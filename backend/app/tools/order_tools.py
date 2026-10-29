"""Order-related tool functions."""
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.db import Order, OrderItem, ToolCall


async def _log_tool_call(
    db: AsyncSession,
    conversation_id: str,
    tool: str,
    args: dict,
    result: dict,
    latency_ms: int,
) -> None:
    """Log a tool call to the database."""
    tc = ToolCall(
        conversation_id=conversation_id,
        tool=tool,
        args_json=args,
        result_json=result,
        latency_ms=latency_ms,
    )
    db.add(tc)
    # Don't flush here — caller manages the session


async def get_order(
    order_id: str,
    customer_id: str,
    db: AsyncSession,
    conversation_id: str = "unknown",
) -> dict:
    """Fetch an order with its items, verifying ownership."""
    start = time.monotonic()
    args = {"order_id": order_id, "customer_id": customer_id}

    try:
        order_uuid = UUID(str(order_id).strip())
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid order ID format '{order_id}'. Order IDs must be valid UUIDs.",
        )

    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_uuid)
    )
    order = result.scalar_one_or_none()

    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if str(order.customer_id) != str(customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this order",
        )

    output = {
        "order_id": str(order.id),
        "status": order.status,
        "total": float(order.total),
        "currency": order.currency,
        "placed_at": order.placed_at.isoformat() if order.placed_at else None,
        "dispatched_at": order.dispatched_at.isoformat() if order.dispatched_at else None,
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
        "address": order.address_json,
        "items": [
            {
                "item_id": str(item.id),
                "sku": item.sku,
                "name": item.name,
                "qty": item.qty,
                "price": float(item.price),
            }
            for item in order.items
        ],
    }

    latency = int((time.monotonic() - start) * 1000)
    await _log_tool_call(db, conversation_id, "get_order", args, output, latency)
    return output


async def track_shipment(
    order_id: str,
    customer_id: str,
    db: AsyncSession,
    conversation_id: str = "unknown",
) -> dict:
    """Return mock carrier tracking data for an order."""
    start = time.monotonic()
    args = {"order_id": order_id}

    try:
        order_uuid = UUID(str(order_id).strip())
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid order ID format '{order_id}'. Order IDs must be valid UUIDs.",
        )

    result = await db.execute(select(Order).where(Order.id == order_uuid))
    order = result.scalar_one_or_none()

    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if str(order.customer_id) != str(customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to track this order",
        )

    if order.status not in ("dispatched", "delivered"):
        output = {
            "order_id": order_id,
            "status": order.status,
            "tracking_available": False,
            "message": f"Tracking not available — order is currently '{order.status}'.",
        }
    else:
        carriers = ["FedEx", "BlueDart", "Delhivery"]
        carrier = random.choice(carriers)
        # Generate a mock tracking number seeded by order_id for determinism
        seed = int(UUID(order_id).int % 10**10)
        tracking_number = f"{carrier[:2].upper()}{seed:010d}"

        if order.dispatched_at:
            eta = order.dispatched_at + timedelta(days=random.randint(2, 5))
        else:
            eta = datetime.now(timezone.utc) + timedelta(days=3)

        output = {
            "order_id": order_id,
            "status": order.status,
            "tracking_available": True,
            "carrier": carrier,
            "tracking_number": tracking_number,
            "estimated_delivery": eta.isoformat(),
            "last_update": "In transit — out for delivery in your city.",
        }

    latency = int((time.monotonic() - start) * 1000)
    await _log_tool_call(db, conversation_id, "track_shipment", args, output, latency)
    return output


async def update_address(
    order_id: str,
    new_address: dict,
    customer_id: str,
    db: AsyncSession,
    conversation_id: str = "unknown",
) -> dict:
    """Update delivery address for orders not yet dispatched."""
    start = time.monotonic()
    args = {"order_id": order_id, "new_address": new_address}

    try:
        order_uuid = UUID(str(order_id).strip())
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid order ID format '{order_id}'. Order IDs must be valid UUIDs.",
        )

    result = await db.execute(select(Order).where(Order.id == order_uuid))
    order = result.scalar_one_or_none()

    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if str(order.customer_id) != str(customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this order",
        )

    updatable_statuses = ("pending", "confirmed", "processing")
    if order.status not in updatable_statuses:
        output = {
            "success": False,
            "order_id": order_id,
            "current_status": order.status,
            "message": (
                f"Cannot update address — order has already been {order.status}. "
                "Address changes are only allowed before dispatch."
            ),
        }
    else:
        order.address_json = new_address
        await db.flush()
        output = {
            "success": True,
            "order_id": order_id,
            "message": "Delivery address updated successfully.",
            "new_address": new_address,
        }

    latency = int((time.monotonic() - start) * 1000)
    await _log_tool_call(db, conversation_id, "update_address", args, output, latency)
    return output
