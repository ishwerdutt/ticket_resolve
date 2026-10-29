"""
Tests for ThreadNest Refund and Replacement Workflows:
- Eligibility boundaries (order status, 30-day window, customer authorization).
- Auto-approval threshold (<= 1000 INR auto-approved vs > 1000 INR queued in approvals).
- Replacement flow (order/item validation and approval queuing).
- Multi-turn LangGraph Agent loops (policy citations, refund decisions, and replacement requests).
100% offline testability with mocked OpenAI API and SQLAlchemy async database sessions.
"""
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.agent.graph import run_agent
from app.models.db import Approval, Order, OrderItem, Refund, Replacement
from app.tools.refund_tools import check_refund_eligibility, create_refund
from app.tools.replacement_tools import create_replacement

# ─── Helpers & Mocks ─────────────────────────────────────────────────────────

def make_uuid() -> str:
    return str(uuid.uuid4())


def make_mock_order(
    order_id: str,
    customer_id: str,
    status: str = "delivered",
    delivered_at: datetime | None = None,
    total: float = 899.0,
) -> MagicMock:
    order = MagicMock(spec=Order)
    order.id = uuid.UUID(order_id)
    order.customer_id = uuid.UUID(customer_id)
    order.status = status
    order.total = Decimal(str(total))
    order.currency = "INR"
    order.placed_at = datetime.now(UTC) - timedelta(days=12)
    order.dispatched_at = datetime.now(UTC) - timedelta(days=8)
    order.delivered_at = delivered_at
    order.address_json = {"line1": "123 MG Road", "city": "Bengaluru", "state": "Karnataka", "pincode": "560001"}
    order.items = []
    return order


def make_mock_item(item_id: str, order_id: str, name: str = "Classic T-Shirt", sku: str = "TN-TSH-001") -> MagicMock:
    item = MagicMock(spec=OrderItem)
    item.id = uuid.UUID(item_id)
    item.order_id = uuid.UUID(order_id)
    item.sku = sku
    item.name = name
    item.qty = 1
    item.price = Decimal("599.00")
    return item


def build_routing_mock_db(order=None, item=None, existing_refund=None, existing_replacement=None, passages=None):
    """
    Intelligent mock DB session routing queries based on statement content.
    Handles single objects, lists, and CTE mappings safely.
    Automatically assigns UUIDs on flush to simulate DB defaults.
    """
    db = AsyncMock()
    db.added_objects = []

    def capture_add(obj):
        db.added_objects.append(obj)

    async def mock_flush():
        for obj in db.added_objects:
            if hasattr(obj, "id") and obj.id is None:
                obj.id = uuid.uuid4()

    db.add = MagicMock(side_effect=capture_add)
    db.flush = AsyncMock(side_effect=mock_flush)
    db.commit = AsyncMock()

    async def mock_execute(statement, params=None):
        stmt_str = str(statement).lower()
        res = MagicMock()

        if "with sparse_search" in stmt_str or "policy_chunks" in stmt_str:
            mappings_mock = MagicMock()
            mappings_mock.all.return_value = passages or []
            res.mappings.return_value = mappings_mock
        elif "order_items" in stmt_str:
            res.scalar_one_or_none.return_value = item
            res.scalars.return_value.all.return_value = [item] if item else []
        elif "refunds" in stmt_str:
            res.scalar_one_or_none.return_value = existing_refund
            res.scalars.return_value.all.return_value = [existing_refund] if existing_refund else []
        elif "replacements" in stmt_str:
            res.scalar_one_or_none.return_value = existing_replacement
            res.scalars.return_value.all.return_value = [existing_replacement] if existing_replacement else []
        elif "orders" in stmt_str:
            res.scalar_one_or_none.return_value = order
            res.scalars.return_value.all.return_value = [order] if order else []
        else:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = []
            res.mappings.return_value.all.return_value = []

        return res

    db.execute = AsyncMock(side_effect=mock_execute)
    return db


# ─── Section 1: Refund Eligibility Boundary Unit Tests ───────────────────────

@pytest.mark.asyncio
async def test_check_refund_eligibility_invalid_uuid():
    """Invalid order UUID format should raise HTTP 400 Bad Request."""
    db = build_routing_mock_db()
    with pytest.raises(HTTPException) as exc:
        await check_refund_eligibility("bad-uuid-123", "damaged", make_uuid(), db)
    assert exc.value.status_code == 400
    assert "Invalid order ID format" in exc.value.detail


@pytest.mark.asyncio
async def test_check_refund_eligibility_order_not_found():
    """Non-existent order should raise HTTP 404 Not Found."""
    db = build_routing_mock_db(order=None)
    with pytest.raises(HTTPException) as exc:
        await check_refund_eligibility(make_uuid(), "damaged", make_uuid(), db)
    assert exc.value.status_code == 404
    assert "Order not found" in exc.value.detail


@pytest.mark.asyncio
async def test_check_refund_eligibility_wrong_customer_forbidden():
    """Order belonging to a different customer should raise HTTP 403 Forbidden."""
    order_id = make_uuid()
    owner_id = make_uuid()
    intruder_id = make_uuid()

    order = make_mock_order(order_id, owner_id)
    db = build_routing_mock_db(order=order)

    with pytest.raises(HTTPException) as exc:
        await check_refund_eligibility(order_id, "size_issue", intruder_id, db)
    assert exc.value.status_code == 403
    assert "permission" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_check_refund_eligibility_status_not_delivered():
    """Order with status != 'delivered' is not eligible (rule REFUND_POLICY_001)."""
    order_id = make_uuid()
    cust_id = make_uuid()
    order = make_mock_order(order_id, cust_id, status="dispatched", delivered_at=None)
    db = build_routing_mock_db(order=order)

    result = await check_refund_eligibility(order_id, "changed_mind", cust_id, db)
    assert result["eligible"] is False
    assert result["max_amount"] == 0.0
    assert result["rule_cited"] == "REFUND_POLICY_001"
    assert "dispatched" in result["reason"].lower()


@pytest.mark.asyncio
async def test_check_refund_eligibility_delivery_date_missing():
    """Delivered order lacking a delivered_at timestamp is rejected."""
    order_id = make_uuid()
    cust_id = make_uuid()
    order = make_mock_order(order_id, cust_id, status="delivered", delivered_at=None)
    db = build_routing_mock_db(order=order)

    result = await check_refund_eligibility(order_id, "damaged", cust_id, db)
    assert result["eligible"] is False
    assert "Delivery date not recorded" in result["reason"]


@pytest.mark.asyncio
async def test_check_refund_eligibility_window_expired_over_30_days():
    """Order delivered 35 days ago exceeds the 30-day window (REFUND_POLICY_002)."""
    order_id = make_uuid()
    cust_id = make_uuid()
    delivery_date = datetime.now(UTC) - timedelta(days=35)
    order = make_mock_order(order_id, cust_id, status="delivered", delivered_at=delivery_date)
    db = build_routing_mock_db(order=order)

    result = await check_refund_eligibility(order_id, "defective", cust_id, db)
    assert result["eligible"] is False
    assert result["rule_cited"] == "REFUND_POLICY_002"
    assert "expired" in result["reason"].lower()


@pytest.mark.asyncio
async def test_check_refund_eligibility_valid_within_30_days():
    """Order delivered 5 days ago is fully eligible (REFUND_POLICY_003)."""
    order_id = make_uuid()
    cust_id = make_uuid()
    delivery_date = datetime.now(UTC) - timedelta(days=5)
    order = make_mock_order(order_id, cust_id, status="delivered", delivered_at=delivery_date, total=1299.0)
    db = build_routing_mock_db(order=order)

    result = await check_refund_eligibility(order_id, "size_too_small", cust_id, db)
    assert result["eligible"] is True
    assert result["max_amount"] == 1299.0
    assert result["rule_cited"] == "REFUND_POLICY_003"
    assert "eligible for a refund" in result["reason"].lower()


# ─── Section 2: Auto-Approval vs Approval Queue Threshold Tests ──────────────

@pytest.mark.asyncio
async def test_create_refund_auto_approve_at_or_below_1000():
    """Refund for amount <= 1000 INR is auto-approved with no Approval record."""
    order_id = make_uuid()
    cust_id = make_uuid()
    conv_id = make_uuid()
    db = build_routing_mock_db()

    result = await create_refund(
        order_id=order_id,
        amount=1000.0,  # exactly at limit
        reason="defective_stitching",
        customer_id=cust_id,
        conversation_id=conv_id,
        db=db,
    )

    assert result["status"] == "approved"
    assert result["requires_approval"] is False
    assert result["approval_id"] is None
    assert "refund_id" in result

    # Verify database additions: 1 Refund, 0 Approval
    refund_objs = [o for o in db.added_objects if isinstance(o, Refund)]
    approval_objs = [o for o in db.added_objects if isinstance(o, Approval)]
    assert len(refund_objs) == 1
    assert refund_objs[0].status == "approved"
    assert len(approval_objs) == 0


@pytest.mark.asyncio
async def test_create_refund_queues_approval_above_1000():
    """Refund for amount > 1000 INR must create an Approval record with status pending."""
    order_id = make_uuid()
    cust_id = make_uuid()
    conv_id = make_uuid()
    db = build_routing_mock_db()

    result = await create_refund(
        order_id=order_id,
        amount=1000.01,  # just above threshold
        reason="wrong_color",
        customer_id=cust_id,
        conversation_id=conv_id,
        db=db,
    )

    assert result["status"] == "pending"
    assert result["requires_approval"] is True
    assert result["approval_id"] is not None

    refund_objs = [o for o in db.added_objects if isinstance(o, Refund)]
    approval_objs = [o for o in db.added_objects if isinstance(o, Approval)]
    assert len(refund_objs) == 1
    assert refund_objs[0].status == "pending"
    assert len(approval_objs) == 1
    assert approval_objs[0].action == "create_refund"
    assert approval_objs[0].status == "pending"


@pytest.mark.asyncio
async def test_create_refund_idempotent_response():
    """Repeated call with identical idempotency key returns existing refund without duplicates."""
    order_id = make_uuid()
    cust_id = make_uuid()
    conv_id = make_uuid()

    existing_ref = MagicMock(spec=Refund)
    existing_ref.id = uuid.uuid4()
    existing_ref.status = "approved"

    db = build_routing_mock_db(existing_refund=existing_ref)

    result = await create_refund(order_id, 800.0, "reason", cust_id, conv_id, db)
    assert result["refund_id"] == str(existing_ref.id)
    assert result["status"] == "approved"
    assert "idempotent" in result["message"].lower()

    # No new Refund or Approval should have been added
    refund_objs = [o for o in db.added_objects if isinstance(o, Refund)]
    assert len(refund_objs) == 0


# ─── Section 3: Replacement Flow Unit Tests ─────────────────────────────────

@pytest.mark.asyncio
async def test_create_replacement_invalid_uuid_and_not_found():
    """create_replacement rejects malformed UUIDs and missing orders."""
    db = build_routing_mock_db()
    with pytest.raises(HTTPException) as exc1:
        await create_replacement("bad-order", make_uuid(), "wrong_item", make_uuid(), "conv", db)
    assert exc1.value.status_code == 400

    with pytest.raises(HTTPException) as exc2:
        await create_replacement(make_uuid(), make_uuid(), "wrong_item", make_uuid(), "conv", db)
    assert exc2.value.status_code == 404
    assert "Order not found" in exc2.value.detail


@pytest.mark.asyncio
async def test_create_replacement_wrong_customer_forbidden():
    """Replacement requested by unauthorized customer raises HTTP 403 Forbidden."""
    order_id = make_uuid()
    owner_id = make_uuid()
    intruder_id = make_uuid()
    item_id = make_uuid()

    order = make_mock_order(order_id, owner_id)
    db = build_routing_mock_db(order=order)

    with pytest.raises(HTTPException) as exc:
        await create_replacement(order_id, item_id, "damaged", intruder_id, "conv", db)
    assert exc.value.status_code == 403
    assert "permission" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_create_replacement_item_not_in_order_rejected():
    """Replacement fails if the requested item is not found in the given order."""
    order_id = make_uuid()
    cust_id = make_uuid()
    order = make_mock_order(order_id, cust_id)
    db = build_routing_mock_db(order=order, item=None)

    with pytest.raises(HTTPException) as exc:
        await create_replacement(order_id, make_uuid(), "damaged", cust_id, "conv", db)
    assert exc.value.status_code == 404
    assert "Order item not found" in exc.value.detail


@pytest.mark.asyncio
async def test_create_replacement_success_queues_approval():
    """Valid replacement creates Replacement (pending) and Approval (pending) records."""
    order_id = make_uuid()
    item_id = make_uuid()
    cust_id = make_uuid()
    conv_id = make_uuid()

    order = make_mock_order(order_id, cust_id)
    item = make_mock_item(item_id, order_id, name="Embroidered Kurta", sku="TN-KRT-002")
    db = build_routing_mock_db(order=order, item=item)

    result = await create_replacement(
        order_id=order_id,
        item_id=item_id,
        reason="torn_sleeve",
        customer_id=cust_id,
        conversation_id=conv_id,
        db=db,
    )

    assert result["status"] == "pending"
    assert result["requires_approval"] is True
    assert result["item_name"] == "Embroidered Kurta"
    assert result["approval_id"] is not None

    repl_objs = [o for o in db.added_objects if isinstance(o, Replacement)]
    appr_objs = [o for o in db.added_objects if isinstance(o, Approval)]
    assert len(repl_objs) == 1
    assert repl_objs[0].status == "pending"
    assert len(appr_objs) == 1
    assert appr_objs[0].action == "create_replacement"
    assert appr_objs[0].status == "pending"


@pytest.mark.asyncio
async def test_create_replacement_idempotent_response():
    """Repeated replacement call returns existing replacement without creating new rows."""
    order_id = make_uuid()
    item_id = make_uuid()
    cust_id = make_uuid()

    order = make_mock_order(order_id, cust_id)
    item = make_mock_item(item_id, order_id)
    existing_rep = MagicMock(spec=Replacement)
    existing_rep.id = uuid.uuid4()
    existing_rep.status = "pending"

    db = build_routing_mock_db(order=order, item=item, existing_replacement=existing_rep)

    res = await create_replacement(order_id, item_id, "damaged", cust_id, "conv", db)
    assert res["replacement_id"] == str(existing_rep.id)
    assert res["requires_approval"] is True
    assert "idempotent" in res["message"].lower()

    repl_objs = [o for o in db.added_objects if isinstance(o, Replacement)]
    assert len(repl_objs) == 0


# ─── Section 4: Multi-Turn LangGraph Agent Flow Integration Tests ───────────

@pytest.mark.asyncio
async def test_agent_flow_policy_inquiry_with_citation_e2e():
    """Multi-turn agent loop: Customer asks policy question -> agent invokes search_policy -> cites section in answer."""
    conv_id = make_uuid()
    cust_id = make_uuid()

    mock_passages = [
        {
            "id": uuid.uuid4(),
            "doc_id": "return_policy",
            "section": "Return Window and Eligibility",
            "text": "ThreadNest accepts returns within 30 days of confirmed delivery for unwashed clothing.",
            "rrf_score": 0.0328,
        }
    ]
    db = build_routing_mock_db(passages=mock_passages)

    # 1. Intent response
    mock_intent = MagicMock()
    mock_intent.choices = [MagicMock(message=MagicMock(content="policy_question"))]

    # 2. Turn 1: Model issues search_policy tool call
    mock_tc = MagicMock()
    mock_tc.id = "call_policy_1"
    mock_tc.function.name = "search_policy"
    mock_tc.function.arguments = json.dumps({"query": "What is the return window?"})

    mock_msg_t1 = MagicMock()
    mock_msg_t1.content = None
    mock_msg_t1.tool_calls = [mock_tc]
    mock_resp_t1 = MagicMock(choices=[MagicMock(message=mock_msg_t1)])

    # 3. Turn 2: Model sees tool output and answers citing policy section
    mock_msg_t2 = MagicMock()
    mock_msg_t2.content = (
        "According to our Return Policy § Return Window and Eligibility, you can return items within 30 days "
        "of delivery as long as tags are attached and the garment is unworn."
    )
    mock_msg_t2.tool_calls = None
    mock_resp_t2 = MagicMock(choices=[MagicMock(message=mock_msg_t2)])

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[mock_intent, mock_resp_t1, mock_resp_t2]
    )

    with patch("app.agent.nodes._get_client", return_value=mock_client), \
         patch("app.tools.policy_tools.aget_embedding", return_value=[0.05] * 1536):

        result = await run_agent(
            conversation_id=conv_id,
            customer_id=cust_id,
            messages=[{"role": "user", "content": "How many days do I have to return an item?"}],
            db=db,
        )

    assert result["final_response"] is not None
    assert "Return Policy § Return Window and Eligibility" in result["final_response"]
    assert result["state"] == "RESOLVED"
    assert result["tool_calls_count"] == 1


@pytest.mark.asyncio
async def test_agent_flow_refund_auto_approve_e2e():
    """Agent loop: Eligible order <= 1000 INR -> check eligibility -> create refund -> auto-approved."""
    conv_id = make_uuid()
    cust_id = make_uuid()
    order_id = make_uuid()

    delivery_date = datetime.now(UTC) - timedelta(days=7)
    order = make_mock_order(order_id, cust_id, status="delivered", delivered_at=delivery_date, total=899.0)
    db = build_routing_mock_db(order=order)

    # 1. Intent
    mock_intent = MagicMock()
    mock_intent.choices = [MagicMock(message=MagicMock(content="refund"))]

    # 2. Turn 1: check_refund_eligibility
    mock_tc1 = MagicMock()
    mock_tc1.id = "call_chk_1"
    mock_tc1.function.name = "check_refund_eligibility"
    mock_tc1.function.arguments = json.dumps({"order_id": order_id, "reason": "damaged_button"})

    mock_resp_t1 = MagicMock(choices=[MagicMock(message=MagicMock(content=None, tool_calls=[mock_tc1]))])

    # 3. Turn 2: create_refund for 899.0 INR (auto-approved)
    mock_tc2 = MagicMock()
    mock_tc2.id = "call_cr_1"
    mock_tc2.function.name = "create_refund"
    mock_tc2.function.arguments = json.dumps({"order_id": order_id, "amount": 899.0, "reason": "damaged_button"})

    mock_resp_t2 = MagicMock(choices=[MagicMock(message=MagicMock(content=None, tool_calls=[mock_tc2]))])

    # 4. Turn 3: Final confirmation message
    mock_msg_final = MagicMock(
        content="I have processed your refund of ₹899.00! It has been auto-approved and will appear in your account in 3-5 days.",
        tool_calls=None,
    )
    mock_resp_t3 = MagicMock(choices=[MagicMock(message=mock_msg_final)])

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[mock_intent, mock_resp_t1, mock_resp_t2, mock_resp_t3]
    )

    with patch("app.agent.nodes._get_client", return_value=mock_client):
        result = await run_agent(
            conversation_id=conv_id,
            customer_id=cust_id,
            messages=[{"role": "user", "content": f"I want a refund for order {order_id}"}],
            db=db,
        )

    assert result["final_response"] is not None
    assert "auto-approved" in result["final_response"].lower()
    assert result["pending_approval_id"] is None
    assert result["tool_calls_count"] == 2


@pytest.mark.asyncio
async def test_agent_flow_refund_approval_queued_e2e():
    """Agent loop: Refund > 1000 INR -> create refund returns approval_id -> agent state becomes AWAITING_APPROVAL."""
    conv_id = make_uuid()
    cust_id = make_uuid()
    order_id = make_uuid()

    delivery_date = datetime.now(UTC) - timedelta(days=4)
    order = make_mock_order(order_id, cust_id, status="delivered", delivered_at=delivery_date, total=2499.0)
    db = build_routing_mock_db(order=order)

    # 1. Intent
    mock_intent = MagicMock()
    mock_intent.choices = [MagicMock(message=MagicMock(content="refund"))]

    # 2. Turn 1: create_refund for 2499.0 INR (exceeds threshold)
    mock_tc = MagicMock()
    mock_tc.id = "call_cr_high"
    mock_tc.function.name = "create_refund"
    mock_tc.function.arguments = json.dumps({"order_id": order_id, "amount": 2499.0, "reason": "fabric_quality"})

    mock_resp_t1 = MagicMock(choices=[MagicMock(message=MagicMock(content=None, tool_calls=[mock_tc]))])

    # 3. Turn 2: Assistant explains the approval queue to the customer
    mock_msg_t2 = MagicMock(
        content="Your refund request for ₹2499.00 has been submitted for staff review because it exceeds ₹1,000. Our team will review and approve it within 1-2 business days.",
        tool_calls=None,
    )
    mock_resp_t2 = MagicMock(choices=[MagicMock(message=mock_msg_t2)])

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=[mock_intent, mock_resp_t1, mock_resp_t2])

    with patch("app.agent.nodes._get_client", return_value=mock_client):
        result = await run_agent(
            conversation_id=conv_id,
            customer_id=cust_id,
            messages=[{"role": "user", "content": f"Refund order {order_id}"}],
            db=db,
        )

    # When tool returns approval_id, state transitions to and remains AWAITING_APPROVAL
    assert result["pending_approval_id"] is not None
    assert result["state"] == "AWAITING_APPROVAL"
    assert result["final_response"] is not None
    assert "review" in result["final_response"].lower() or "approval" in result["final_response"].lower()


@pytest.mark.asyncio
async def test_agent_flow_replacement_queued_e2e():
    """Agent loop: create_replacement returns approval_id -> agent state transitions to AWAITING_APPROVAL."""
    conv_id = make_uuid()
    cust_id = make_uuid()
    order_id = make_uuid()
    item_id = make_uuid()

    order = make_mock_order(order_id, cust_id, status="delivered")
    item = make_mock_item(item_id, order_id, name="Linen Shirt")
    db = build_routing_mock_db(order=order, item=item)

    # 1. Intent
    mock_intent = MagicMock()
    mock_intent.choices = [MagicMock(message=MagicMock(content="replacement"))]

    # 2. Turn 1: create_replacement tool call
    mock_tc = MagicMock()
    mock_tc.id = "call_repl_1"
    mock_tc.function.name = "create_replacement"
    mock_tc.function.arguments = json.dumps({"order_id": order_id, "item_id": item_id, "reason": "wrong_size"})

    mock_resp_t1 = MagicMock(choices=[MagicMock(message=MagicMock(content=None, tool_calls=[mock_tc]))])

    # 3. Turn 2: Assistant explains staff review process for replacement
    mock_msg_t2 = MagicMock(
        content="Your replacement request for Linen Shirt has been submitted for staff review. Our team will verify and approve it within 1-2 business days.",
        tool_calls=None,
    )
    mock_resp_t2 = MagicMock(choices=[MagicMock(message=mock_msg_t2)])

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=[mock_intent, mock_resp_t1, mock_resp_t2])

    with patch("app.agent.nodes._get_client", return_value=mock_client):
        result = await run_agent(
            conversation_id=conv_id,
            customer_id=cust_id,
            messages=[{"role": "user", "content": f"Can I get a replacement for item {item_id} in order {order_id}?"}],
            db=db,
        )

    assert result["pending_approval_id"] is not None
    assert result["state"] == "AWAITING_APPROVAL"
    assert result["final_response"] is not None
    assert "review" in result["final_response"].lower() or "approve" in result["final_response"].lower()
