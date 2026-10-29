"""
Tests for ThreadNest tool functions.

Uses pytest-asyncio with MagicMock to simulate DB sessions.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_uuid() -> str:
    return str(uuid.uuid4())


def make_mock_db():
    """Create a mock async DB session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def make_mock_order(
    order_id: str,
    customer_id: str,
    status: str = "delivered",
    delivered_at: datetime | None = None,
    total: float = 1500.0,
) -> MagicMock:
    order = MagicMock()
    order.id = uuid.UUID(order_id)
    order.customer_id = uuid.UUID(customer_id)
    order.status = status
    order.total = Decimal(str(total))
    order.currency = "INR"
    order.placed_at = datetime.now(timezone.utc) - timedelta(days=10)
    order.dispatched_at = datetime.now(timezone.utc) - timedelta(days=7)
    order.delivered_at = delivered_at
    order.address_json = {"line1": "Test", "city": "Mumbai", "state": "Maharashtra", "pincode": "400001"}
    order.items = []
    return order


def make_mock_item(item_id: str, order_id: str) -> MagicMock:
    item = MagicMock()
    item.id = uuid.UUID(item_id)
    item.order_id = uuid.UUID(order_id)
    item.sku = "TN-TSH-001"
    item.name = "ThreadNest Classic T-Shirt"
    item.qty = 1
    item.price = Decimal("599.00")
    return item


def mock_execute_returning(obj):
    """Helper: mock db.execute() to return a result that yields `obj` from scalar_one_or_none()."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = obj
    result_mock.scalars.return_value.all.return_value = [obj] if obj else []

    db = make_mock_db()
    db.execute = AsyncMock(return_value=result_mock)
    return db


# ─── Test 1: get_order raises 403 for wrong customer ─────────────────────────

@pytest.mark.asyncio
async def test_get_order_wrong_customer():
    """get_order should raise HTTP 403 when customer_id doesn't match."""
    from fastapi import HTTPException

    from app.tools.order_tools import get_order

    order_id = make_uuid()
    real_customer_id = make_uuid()
    attacker_customer_id = make_uuid()

    order = make_mock_order(order_id, real_customer_id)
    db = mock_execute_returning(order)

    with pytest.raises(HTTPException) as exc_info:
        await get_order(
            order_id=order_id,
            customer_id=attacker_customer_id,
            db=db,
            conversation_id="test-conv",
        )

    assert exc_info.value.status_code == 403
    assert "permission" in exc_info.value.detail.lower()


# ─── Test 2: check_refund_eligibility — order too old ────────────────────────

@pytest.mark.asyncio
async def test_check_refund_eligibility_too_old():
    """Orders delivered 35 days ago should return eligible=False."""
    from app.tools.refund_tools import check_refund_eligibility

    order_id = make_uuid()
    customer_id = make_uuid()

    delivered_at = datetime.now(timezone.utc) - timedelta(days=35)
    order = make_mock_order(order_id, customer_id, status="delivered", delivered_at=delivered_at)
    db = mock_execute_returning(order)

    result = await check_refund_eligibility(
        order_id=order_id,
        reason="damaged",
        customer_id=customer_id,
        db=db,
        conversation_id="test-conv",
    )

    assert result["eligible"] is False
    assert result["max_amount"] == 0.0
    assert "30" in result["reason"]  # mentions 30-day window
    assert result["rule_cited"] == "REFUND_POLICY_002"


# ─── Test 3: check_refund_eligibility — not delivered ────────────────────────

@pytest.mark.asyncio
async def test_check_refund_eligibility_not_delivered():
    """Orders with status 'dispatched' should return eligible=False."""
    from app.tools.refund_tools import check_refund_eligibility

    order_id = make_uuid()
    customer_id = make_uuid()

    order = make_mock_order(order_id, customer_id, status="dispatched", delivered_at=None)
    db = mock_execute_returning(order)

    result = await check_refund_eligibility(
        order_id=order_id,
        reason="wrong_item",
        customer_id=customer_id,
        db=db,
        conversation_id="test-conv",
    )

    assert result["eligible"] is False
    assert result["max_amount"] == 0.0
    assert "dispatched" in result["reason"].lower()
    assert result["rule_cited"] == "REFUND_POLICY_001"


# ─── Test 4: create_refund — auto-approve for amount <= 1000 ─────────────────

@pytest.mark.asyncio
async def test_create_refund_auto_approve():
    """Refunds <= REFUND_AUTO_APPROVE_LIMIT should be auto-approved."""
    from app.tools.refund_tools import create_refund

    order_id = make_uuid()
    customer_id = make_uuid()
    conversation_id = make_uuid()
    amount = settings.REFUND_AUTO_APPROVE_LIMIT  # exactly at limit

    db = make_mock_db()

    # First execute call: check for existing refund → None
    # Subsequent calls: no existing refund
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=no_result)

    # Capture the Refund object that gets added
    added_objects = []
    original_add = db.add

    def capture_add(obj):
        added_objects.append(obj)

    db.add = MagicMock(side_effect=capture_add)

    result = await create_refund(
        order_id=order_id,
        amount=amount,
        reason="damaged",
        customer_id=customer_id,
        conversation_id=conversation_id,
        db=db,
    )

    assert result["status"] == "approved"
    assert result["requires_approval"] is False
    assert result["approval_id"] is None
    assert "refund_id" in result

    # Should only add one object (the Refund), not an Approval
    # (ToolCall is also added, so filter by type)
    from app.models.db import Approval, Refund
    approval_objects = [o for o in added_objects if isinstance(o, Approval)]
    assert len(approval_objects) == 0, "No approval should be created for auto-approved refunds"


# ─── Test 5: create_refund — needs approval for amount > 1000 ────────────────

@pytest.mark.asyncio
async def test_create_refund_needs_approval():
    """Refunds > REFUND_AUTO_APPROVE_LIMIT should create an approval row."""
    from app.tools.refund_tools import create_refund

    order_id = make_uuid()
    customer_id = make_uuid()
    conversation_id = make_uuid()
    amount = settings.REFUND_AUTO_APPROVE_LIMIT + 0.01  # just over limit

    db = make_mock_db()
    no_result = MagicMock()
    no_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=no_result)

    added_objects = []

    def capture_add(obj):
        added_objects.append(obj)

    db.add = MagicMock(side_effect=capture_add)

    result = await create_refund(
        order_id=order_id,
        amount=amount,
        reason="not_as_described",
        customer_id=customer_id,
        conversation_id=conversation_id,
        db=db,
    )

    assert result["status"] == "pending"
    assert result["requires_approval"] is True

    # An Approval object should have been added
    from app.models.db import Approval
    approval_objects = [o for o in added_objects if isinstance(o, Approval)]
    assert len(approval_objects) == 1, "One approval should be created for large refunds"
    assert approval_objects[0].action == "create_refund"
    assert approval_objects[0].status == "pending"
