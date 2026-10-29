"""
Milestone 2 Challenger Adversarial Stress Test Suite.
Empirical verification of:
1. Exact refund boundaries (1000.00 auto-approved vs 1000.01 queued in approvals).
2. Exact refund delivery date boundaries (30 days eligible vs 31 days rejected).
3. Non-delivered order status guards (dispatched, pending, missing delivered_at).
4. Replacement authorization and item containment (valid queued, item mismatch 404, cross-customer 403).
5. Multi-turn policy citation loop and format conformance ("According to our [Doc] § [Section], ...").
6. Real database pgvector + BM25 hybrid policy search on localhost:5434.
"""
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.agent.graph import run_agent
from app.agent.nodes import _dispatch_tool
from app.agent.prompts import SYSTEM_PROMPT
from app.config import settings
from app.models.db import Approval, Order, OrderItem, Refund, Replacement
from app.tools.policy_tools import search_policy
from app.tools.refund_tools import check_refund_eligibility, create_refund
from app.tools.replacement_tools import create_replacement


def make_uuid() -> str:
    return str(uuid.uuid4())


def make_order(
    order_id: str,
    customer_id: str,
    status: str = "delivered",
    delivered_at: datetime | None = None,
    total: float = 1500.0,
) -> MagicMock:
    order = MagicMock(spec=Order)
    order.id = uuid.UUID(order_id)
    order.customer_id = uuid.UUID(customer_id)
    order.status = status
    order.total = Decimal(str(total))
    order.currency = "INR"
    order.placed_at = datetime.now(UTC) - timedelta(days=15)
    order.dispatched_at = datetime.now(UTC) - timedelta(days=10)
    order.delivered_at = delivered_at
    order.address_json = {"line1": "123 Commercial St", "city": "Bengaluru", "state": "Karnataka", "pincode": "560001"}
    order.items = []
    return order


def make_item(item_id: str, order_id: str, name: str = "Linen Kurta", sku: str = "TN-KRT-101") -> MagicMock:
    item = MagicMock(spec=OrderItem)
    item.id = uuid.UUID(item_id)
    item.order_id = uuid.UUID(order_id)
    item.sku = sku
    item.name = name
    item.qty = 1
    item.price = Decimal("899.00")
    return item


def build_harness_mock_db(order=None, item=None, existing_refund=None, existing_replacement=None, passages=None):
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


# ═══════════════════════════════════════════════════════════════════════════════
# 1. EMPIRICAL REFUND BOUNDARY TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_refund_exact_boundary_1000_00_inr():
    """Exact ₹1,000.00 INR refund must be auto-approved with NO approval row."""
    order_id = make_uuid()
    cust_id = make_uuid()
    conv_id = make_uuid()
    db = build_harness_mock_db()

    result = await create_refund(
        order_id=order_id,
        amount=1000.00,
        reason="size_mismatch",
        customer_id=cust_id,
        conversation_id=conv_id,
        db=db,
    )

    assert result["status"] == "approved"
    assert result["requires_approval"] is False
    assert result["approval_id"] is None
    assert "auto-approved" in result["message"]

    refund_objs = [o for o in db.added_objects if isinstance(o, Refund)]
    approval_objs = [o for o in db.added_objects if isinstance(o, Approval)]
    assert len(refund_objs) == 1
    assert refund_objs[0].status == "approved"
    assert len(approval_objs) == 0, "No approval record should be created for ₹1,000.00"


@pytest.mark.asyncio
async def test_refund_exact_boundary_1000_01_inr():
    """Exact ₹1,000.01 INR refund must be queued with status 'pending' and approval_id created."""
    order_id = make_uuid()
    cust_id = make_uuid()
    conv_id = make_uuid()
    db = build_harness_mock_db()

    result = await create_refund(
        order_id=order_id,
        amount=1000.01,
        reason="fabric_flaw",
        customer_id=cust_id,
        conversation_id=conv_id,
        db=db,
    )

    assert result["status"] == "pending"
    assert result["requires_approval"] is True
    assert result["approval_id"] is not None
    assert "submitted for staff review" in result["message"]

    refund_objs = [o for o in db.added_objects if isinstance(o, Refund)]
    approval_objs = [o for o in db.added_objects if isinstance(o, Approval)]
    assert len(refund_objs) == 1
    assert refund_objs[0].status == "pending"
    assert len(approval_objs) == 1
    assert approval_objs[0].action == "create_refund"
    assert approval_objs[0].status == "pending"
    assert str(approval_objs[0].id) == result["approval_id"]


@pytest.mark.asyncio
async def test_refund_eligibility_delivered_exactly_30_days_ago():
    """Order delivered 30 days ago is within the return window and eligible."""
    order_id = make_uuid()
    cust_id = make_uuid()
    delivered_date = datetime.now(UTC) - timedelta(days=30, hours=0)
    order = make_order(order_id, cust_id, status="delivered", delivered_at=delivered_date, total=1499.0)
    db = build_harness_mock_db(order=order)

    result = await check_refund_eligibility(order_id, "fit_issue", cust_id, db)
    assert result["eligible"] is True
    assert result["rule_cited"] == "REFUND_POLICY_003"
    assert result["max_amount"] == 1499.0


@pytest.mark.asyncio
async def test_refund_eligibility_delivered_30_days_23_hours_ago():
    """Order delivered 30 days and 23 hours ago has days_since_delivery == 30 and remains eligible."""
    order_id = make_uuid()
    cust_id = make_uuid()
    delivered_date = datetime.now(UTC) - timedelta(days=30, hours=23)
    order = make_order(order_id, cust_id, status="delivered", delivered_at=delivered_date, total=999.0)
    db = build_harness_mock_db(order=order)

    result = await check_refund_eligibility(order_id, "color_faded", cust_id, db)
    assert result["eligible"] is True
    assert result["rule_cited"] == "REFUND_POLICY_003"
    assert result["max_amount"] == 999.0


@pytest.mark.asyncio
async def test_refund_eligibility_delivered_exactly_31_days_ago():
    """Order delivered 31 days ago is past the return window and rejected with REFUND_POLICY_002."""
    order_id = make_uuid()
    cust_id = make_uuid()
    delivered_date = datetime.now(UTC) - timedelta(days=31, hours=0)
    order = make_order(order_id, cust_id, status="delivered", delivered_at=delivered_date, total=1499.0)
    db = build_harness_mock_db(order=order)

    result = await check_refund_eligibility(order_id, "size_issue", cust_id, db)
    assert result["eligible"] is False
    assert result["rule_cited"] == "REFUND_POLICY_002"
    assert result["max_amount"] == 0.0
    assert "expired" in result["reason"].lower()


@pytest.mark.asyncio
async def test_refund_eligibility_not_delivered_dispatched():
    """Order with status 'dispatched' is rejected with REFUND_POLICY_001."""
    order_id = make_uuid()
    cust_id = make_uuid()
    order = make_order(order_id, cust_id, status="dispatched", delivered_at=None)
    db = build_harness_mock_db(order=order)

    result = await check_refund_eligibility(order_id, "late_arrival", cust_id, db)
    assert result["eligible"] is False
    assert result["rule_cited"] == "REFUND_POLICY_001"
    assert "dispatched" in result["reason"].lower()


@pytest.mark.asyncio
async def test_refund_eligibility_not_delivered_pending():
    """Order with status 'pending' is rejected with REFUND_POLICY_001."""
    order_id = make_uuid()
    cust_id = make_uuid()
    order = make_order(order_id, cust_id, status="pending", delivered_at=None)
    db = build_harness_mock_db(order=order)

    result = await check_refund_eligibility(order_id, "mind_change", cust_id, db)
    assert result["eligible"] is False
    assert result["rule_cited"] == "REFUND_POLICY_001"
    assert "pending" in result["reason"].lower()


@pytest.mark.asyncio
async def test_refund_eligibility_delivered_missing_timestamp():
    """Order status 'delivered' but delivered_at is None is rejected with REFUND_POLICY_001."""
    order_id = make_uuid()
    cust_id = make_uuid()
    order = make_order(order_id, cust_id, status="delivered", delivered_at=None)
    db = build_harness_mock_db(order=order)

    result = await check_refund_eligibility(order_id, "damaged", cust_id, db)
    assert result["eligible"] is False
    assert result["rule_cited"] == "REFUND_POLICY_001"
    assert "Delivery date not recorded" in result["reason"]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. EMPIRICAL REPLACEMENT WORKFLOW TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_replacement_valid_item_queued_in_approvals():
    """Valid item in customer order must create pending Replacement and pending Approval rows."""
    order_id = make_uuid()
    item_id = make_uuid()
    cust_id = make_uuid()
    conv_id = make_uuid()

    order = make_order(order_id, cust_id, status="delivered")
    item = make_item(item_id, order_id, name="Silk Saree", sku="TN-SAR-005")
    db = build_harness_mock_db(order=order, item=item)

    result = await create_replacement(
        order_id=order_id,
        item_id=item_id,
        reason="torn_pallu",
        customer_id=cust_id,
        conversation_id=conv_id,
        db=db,
    )

    assert result["status"] == "pending"
    assert result["requires_approval"] is True
    assert result["approval_id"] is not None
    assert result["item_name"] == "Silk Saree"

    repl_objs = [o for o in db.added_objects if isinstance(o, Replacement)]
    appr_objs = [o for o in db.added_objects if isinstance(o, Approval)]
    assert len(repl_objs) == 1
    assert repl_objs[0].status == "pending"
    assert len(appr_objs) == 1
    assert appr_objs[0].action == "create_replacement"
    assert appr_objs[0].status == "pending"
    assert appr_objs[0].args_json["item_sku"] == "TN-SAR-005"


@pytest.mark.asyncio
async def test_replacement_item_not_in_order_404():
    """Item not belonging to the order must raise HTTP 404."""
    order_id = make_uuid()
    random_item_id = make_uuid()
    cust_id = make_uuid()

    order = make_order(order_id, cust_id, status="delivered")
    # DB finds the order, but order_items query returns None
    db = build_harness_mock_db(order=order, item=None)

    with pytest.raises(HTTPException) as exc:
        await create_replacement(order_id, random_item_id, "wrong_color", cust_id, "conv", db)

    assert exc.value.status_code == 404
    assert "Order item not found or does not belong to this order" in exc.value.detail


@pytest.mark.asyncio
async def test_replacement_cross_customer_forbidden_403():
    """Replacement request by another customer must raise HTTP 403."""
    order_id = make_uuid()
    item_id = make_uuid()
    owner_id = make_uuid()
    intruder_id = make_uuid()

    order = make_order(order_id, owner_id, status="delivered")
    db = build_harness_mock_db(order=order)

    with pytest.raises(HTTPException) as exc:
        await create_replacement(order_id, item_id, "damaged", intruder_id, "conv", db)

    assert exc.value.status_code == 403
    assert "permission" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_replacement_dispatch_tool_catches_404_gracefully():
    """Agent step tool dispatcher must convert 404 into structured dict without crashing."""
    order_id = make_uuid()
    item_id = make_uuid()
    cust_id = make_uuid()

    order = make_order(order_id, cust_id, status="delivered")
    db = build_harness_mock_db(order=order, item=None)

    tool_args = {"order_id": order_id, "item_id": item_id, "reason": "damaged"}
    result = await _dispatch_tool(
        tool_name="create_replacement",
        tool_args=tool_args,
        customer_id=cust_id,
        conversation_id="conv-1",
        db=db,
    )

    assert isinstance(result, dict)
    assert result.get("status_code") == 404
    assert "Order item not found" in result.get("error", "")


@pytest.mark.asyncio
async def test_replacement_dispatch_tool_catches_403_gracefully():
    """Agent step tool dispatcher must convert 403 into structured dict without crashing."""
    order_id = make_uuid()
    item_id = make_uuid()
    owner_id = make_uuid()
    intruder_id = make_uuid()

    order = make_order(order_id, owner_id, status="delivered")
    db = build_harness_mock_db(order=order)

    tool_args = {"order_id": order_id, "item_id": item_id, "reason": "damaged"}
    result = await _dispatch_tool(
        tool_name="create_replacement",
        tool_args=tool_args,
        customer_id=intruder_id,
        conversation_id="conv-1",
        db=db,
    )

    assert isinstance(result, dict)
    assert result.get("status_code") == 403
    assert "permission" in result.get("error", "").lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. EMPIRICAL MULTI-TURN CITATION & PROMPT COMPLIANCE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

def test_system_prompt_mandates_citation_format():
    """Verify system prompt contains the exact mandatory citation format and policy search rule."""
    assert "According to our [Document Name] § [Section Name], ..." in SYSTEM_PROMPT
    assert "MANDATORY POLICY SEARCH" in SYSTEM_PROMPT
    assert "MANDATORY POLICY CITATIONS" in SYSTEM_PROMPT
    assert "SEQUENTIAL REFUND ELIGIBILITY" in SYSTEM_PROMPT
    assert "REFUND_AUTO_APPROVE_LIMIT" in dir(settings)
    assert settings.REFUND_AUTO_APPROVE_LIMIT == 1000.0


@pytest.mark.asyncio
async def test_agent_multi_turn_policy_citations_e2e():
    """
    Stress-test multi-turn conversational loop:
    Turn 1: Customer asks about return policy -> agent calls search_policy -> cites Return Policy § Return Window & Eligibility.
    Turn 2: Customer asks follow-up on warranty -> agent calls search_policy -> cites Warranty & Quality Guarantee § 6-Month Coverage.
    """
    conv_id = make_uuid()
    cust_id = make_uuid()

    # Passages returned for Turn 1
    passages_t1 = [
        {
            "id": uuid.uuid4(),
            "doc_id": "return_policy",
            "section": "Return Window & Eligibility",
            "text": "ThreadNest accepts returns within 30 days of confirmed delivery for unwashed clothing with original tags attached.",
            "rrf_score": 0.033,
        }
    ]
    # Passages returned for Turn 2
    passages_t2 = [
        {
            "id": uuid.uuid4(),
            "doc_id": "warranty_guarantee",
            "section": "6-Month Coverage",
            "text": "ThreadNest provides a 6-month quality guarantee covering manufacturing defects, stitching unraveling, and zipper failures.",
            "rrf_score": 0.032,
        }
    ]

    # --- Turn 1 Execution ---
    db_t1 = build_harness_mock_db(passages=passages_t1)

    mock_intent_t1 = MagicMock()
    mock_intent_t1.choices = [MagicMock(message=MagicMock(content="policy_question"))]

    tc_t1 = MagicMock()
    tc_t1.id = "tc_p1"
    tc_t1.function.name = "search_policy"
    tc_t1.function.arguments = json.dumps({"query": "return window and tags"})

    resp_call_t1 = MagicMock(choices=[MagicMock(message=MagicMock(content=None, tool_calls=[tc_t1]))])
    resp_answer_t1 = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content="According to our Return Policy § Return Window & Eligibility, you can return items within 30 days of delivery with tags attached.",
                    tool_calls=None,
                )
            )
        ]
    )

    client_t1 = AsyncMock()
    client_t1.chat.completions.create = AsyncMock(
        side_effect=[mock_intent_t1, resp_call_t1, resp_answer_t1]
    )

    with patch("app.agent.nodes._get_client", return_value=client_t1), \
         patch("app.tools.policy_tools.aget_embedding", return_value=[0.01] * 1536):

        result_t1 = await run_agent(
            conversation_id=conv_id,
            customer_id=cust_id,
            messages=[{"role": "user", "content": "How long do I have to return an item?"}],
            db=db_t1,
        )

    assert result_t1["final_response"] is not None
    assert "According to our Return Policy § Return Window & Eligibility" in result_t1["final_response"]
    assert result_t1["state"] == "RESOLVED"

    # --- Turn 2 Execution (Follow-up Turn) ---
    db_t2 = build_harness_mock_db(passages=passages_t2)

    mock_intent_t2 = MagicMock()
    mock_intent_t2.choices = [MagicMock(message=MagicMock(content="policy_question"))]

    tc_t2 = MagicMock()
    tc_t2.id = "tc_p2"
    tc_t2.function.name = "search_policy"
    tc_t2.function.arguments = json.dumps({"query": "defective stitching warranty period"})

    resp_call_t2 = MagicMock(choices=[MagicMock(message=MagicMock(content=None, tool_calls=[tc_t2]))])
    resp_answer_t2 = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content="According to our Warranty & Quality Guarantee § 6-Month Coverage, manufacturing defects and stitching issues are covered for 6 months.",
                    tool_calls=None,
                )
            )
        ]
    )

    client_t2 = AsyncMock()
    client_t2.chat.completions.create = AsyncMock(
        side_effect=[mock_intent_t2, resp_call_t2, resp_answer_t2]
    )

    # Accumulate conversation history from Turn 1
    messages_t2 = list(result_t1["messages"]) + [
        {"role": "user", "content": "What if the stitching breaks after 2 months?"}
    ]

    with patch("app.agent.nodes._get_client", return_value=client_t2), \
         patch("app.tools.policy_tools.aget_embedding", return_value=[0.02] * 1536):

        result_t2 = await run_agent(
            conversation_id=conv_id,
            customer_id=cust_id,
            messages=messages_t2,
            db=db_t2,
        )

    assert result_t2["final_response"] is not None
    assert "According to our Warranty & Quality Guarantee § 6-Month Coverage" in result_t2["final_response"]
    assert result_t2["state"] == "RESOLVED"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. LIVE DATABASE HYBRID POLICY SEARCH INTEGRATION TEST
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_live_postgres_hybrid_policy_search():
    """Empirical integration test against running Postgres 16 + pgvector container on port 5434."""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with AsyncSession(engine) as session:
        # Search live indexed policy documents
        result = await search_policy("return window unworn items tags", db=session, top_k=3)

        assert result is not None
        assert "passages" in result
        assert len(result["passages"]) > 0
        top = result["passages"][0]
        assert "doc_id" in top
        assert "section" in top
        assert "citation" in top
        assert "§" in top["citation"]
        assert top["score"] > 0
    await engine.dispose()
