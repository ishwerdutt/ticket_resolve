"""Week 2 Tests: Tool layer validation, authorization, and order status agent loop."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.agent.nodes import _dispatch_tool
from app.models.schemas import (
    AddressModel,
    GetOrderInput,
    TrackShipmentInput,
    UpdateAddressInput,
)
from app.tools.order_tools import get_order, track_shipment, update_address


def make_uuid() -> str:
    return str(uuid.uuid4())


def make_mock_order(
    order_id: str,
    customer_id: str,
    status: str = "dispatched",
    dispatched_at: datetime | None = None,
    delivered_at: datetime | None = None,
    address_json: dict | None = None,
):
    order = MagicMock()
    order.id = uuid.UUID(order_id)
    order.customer_id = uuid.UUID(customer_id)
    order.status = status
    order.total = Decimal("1499.00")
    order.currency = "INR"
    order.placed_at = datetime.now(timezone.utc) - timedelta(days=5)
    order.dispatched_at = dispatched_at or (datetime.now(timezone.utc) - timedelta(days=2))
    order.delivered_at = delivered_at
    order.address_json = address_json or {
        "line1": "123 MG Road",
        "city": "Bengaluru",
        "state": "Karnataka",
        "pincode": "560001",
    }
    order.items = []
    return order


def make_mock_db(order=None):
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = order
    result_mock.scalars.return_value.all.return_value = [order] if order else []
    db.execute = AsyncMock(return_value=result_mock)
    return db


# ─── 1. Tool Input Validation & Error Handling ──────────────────────────────

@pytest.mark.asyncio
async def test_get_order_invalid_uuid():
    """get_order raises 400 when an invalid UUID string is provided."""
    db = make_mock_db()
    with pytest.raises(HTTPException) as exc:
        await get_order(
            order_id="not-a-valid-uuid",
            customer_id=make_uuid(),
            db=db,
        )
    assert exc.value.status_code == 400
    assert "Invalid order ID format" in exc.value.detail


@pytest.mark.asyncio
async def test_dispatch_tool_validation_error():
    """_dispatch_tool catches Pydantic validation errors before calling the tool."""
    db = make_mock_db()
    # Missing required 'order_id'
    result = await _dispatch_tool(
        tool_name="get_order",
        tool_args={},
        customer_id=make_uuid(),
        conversation_id="conv-1",
        db=db,
    )
    assert "error" in result
    assert "Invalid arguments for get_order" in result["error"]


@pytest.mark.asyncio
async def test_dispatch_tool_catches_http_forbidden():
    """_dispatch_tool catches HTTPException and returns a structured error object."""
    order_id = make_uuid()
    customer_a = make_uuid()
    customer_b = make_uuid()
    order = make_mock_order(order_id, customer_a)
    db = make_mock_db(order)

    result = await _dispatch_tool(
        tool_name="get_order",
        tool_args={"order_id": order_id},
        customer_id=customer_b,
        conversation_id="conv-1",
        db=db,
    )
    assert result["status_code"] == 403
    assert "permission" in result["error"].lower()


# ─── 2. Order Tracking & Shipment Logic ─────────────────────────────────────

@pytest.mark.asyncio
async def test_track_shipment_dispatched_order():
    """track_shipment returns carrier, tracking number, and ETA for dispatched orders."""
    order_id = make_uuid()
    customer_id = make_uuid()
    order = make_mock_order(order_id, customer_id, status="dispatched")
    db = make_mock_db(order)

    result = await track_shipment(
        order_id=order_id,
        customer_id=customer_id,
        db=db,
        conversation_id="conv-1",
    )
    assert result["tracking_available"] is True
    assert result["carrier"] in ["FedEx", "BlueDart", "Delhivery"]
    assert "tracking_number" in result
    assert "estimated_delivery" in result


@pytest.mark.asyncio
async def test_track_shipment_pending_order():
    """track_shipment indicates tracking unavailable when order has not shipped."""
    order_id = make_uuid()
    customer_id = make_uuid()
    order = make_mock_order(order_id, customer_id, status="pending")
    db = make_mock_db(order)

    result = await track_shipment(
        order_id=order_id,
        customer_id=customer_id,
        db=db,
        conversation_id="conv-1",
    )
    assert result["tracking_available"] is False
    assert "pending" in result["message"]


# ─── 3. Address Update Rules ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_address_pre_dispatch_success():
    """update_address succeeds for pending or confirmed orders."""
    order_id = make_uuid()
    customer_id = make_uuid()
    order = make_mock_order(order_id, customer_id, status="pending")
    db = make_mock_db(order)

    new_addr = {
        "line1": "Flat 4B, Sunrise Apts",
        "line2": "Indiranagar",
        "city": "Bengaluru",
        "state": "Karnataka",
        "pincode": "560038",
    }

    result = await update_address(
        order_id=order_id,
        new_address=new_addr,
        customer_id=customer_id,
        db=db,
        conversation_id="conv-1",
    )
    assert result["success"] is True
    assert order.address_json == new_addr


@pytest.mark.asyncio
async def test_update_address_post_dispatch_rejected():
    """update_address is rejected if order is already dispatched."""
    order_id = make_uuid()
    customer_id = make_uuid()
    order = make_mock_order(order_id, customer_id, status="dispatched")
    db = make_mock_db(order)

    new_addr = {
        "line1": "Flat 4B, Sunrise Apts",
        "city": "Bengaluru",
        "state": "Karnataka",
        "pincode": "560038",
    }

    result = await update_address(
        order_id=order_id,
        new_address=new_addr,
        customer_id=customer_id,
        db=db,
        conversation_id="conv-1",
    )
    assert result["success"] is False
    assert "dispatched" in result["message"]


# ─── 4. Single-Agent Order Status Execution Loop ─────────────────────────────

@pytest.mark.asyncio
async def test_order_status_agent_loop_e2e():
    """Simulate single-agent loop for order status using mock OpenAI client."""
    from app.agent.graph import run_agent

    order_id = make_uuid()
    customer_id = make_uuid()
    conv_id = make_uuid()

    order = make_mock_order(order_id, customer_id, status="dispatched")
    db = make_mock_db(order)

    # First turn: customer asks where order is
    messages = [{"role": "user", "content": f"Where is my order {order_id}?"}]

    # Mock tool call response from OpenAI: call get_order, then return assistant answer
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_abc123"
    mock_tool_call.function.name = "get_order"
    mock_tool_call.function.arguments = json.dumps({"order_id": order_id})

    # Turn 1: model returns tool call to get_order
    mock_msg_turn1 = MagicMock()
    mock_msg_turn1.content = None
    mock_msg_turn1.tool_calls = [mock_tool_call]

    # Turn 2: model sees tool output and answers user
    mock_msg_turn2 = MagicMock()
    mock_msg_turn2.content = f"Your order #{order_id[:8]} has been dispatched and is currently in transit!"
    mock_msg_turn2.tool_calls = None

    mock_resp1 = MagicMock()
    mock_resp1.choices = [MagicMock(message=mock_msg_turn1)]
    mock_resp2 = MagicMock()
    mock_resp2.choices = [MagicMock(message=mock_msg_turn2)]

    # Intent classifier mock response
    mock_intent_resp = MagicMock()
    mock_intent_resp.choices = [MagicMock(message=MagicMock(content="order_status"))]

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[mock_intent_resp, mock_resp1, mock_resp2]
    )

    with patch("app.agent.nodes._get_client", return_value=mock_client):
        result = await run_agent(
            conversation_id=conv_id,
            customer_id=customer_id,
            messages=messages,
            db=db,
        )

    assert result["final_response"] is not None
    assert "dispatched" in result["final_response"]
    assert result["state"] == "RESOLVED"
    assert result["tool_calls_count"] == 1
