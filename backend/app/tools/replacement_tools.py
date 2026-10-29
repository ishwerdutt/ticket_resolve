"""Replacement-related tool functions."""
import time
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Approval, Order, OrderItem, Replacement, ToolCall


async def _log_tool_call(
    db: AsyncSession,
    conversation_id: str,
    tool: str,
    args: dict,
    result: dict,
    latency_ms: int,
) -> None:
    tc = ToolCall(
        conversation_id=conversation_id,
        tool=tool,
        args_json=args,
        result_json=result,
        latency_ms=latency_ms,
    )
    db.add(tc)


async def create_replacement(
    order_id: str,
    item_id: str,
    reason: str,
    customer_id: str,
    conversation_id: str,
    db: AsyncSession,
) -> dict:
    """
    Create a replacement for a wrong or damaged item.

    - Verifies order ownership and item belongs to the order.
    - Idempotency key prevents duplicate replacements.
    - Always creates an approval row (medium-risk action).
    """
    start = time.monotonic()
    args = {"order_id": order_id, "item_id": item_id, "reason": reason}

    try:
        order_uuid = UUID(str(order_id).strip())
        item_uuid = UUID(str(item_id).strip())
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid ID format. Order and item IDs must be valid UUIDs.",
        )

    # Verify order
    order_result = await db.execute(select(Order).where(Order.id == order_uuid))
    order = order_result.scalar_one_or_none()

    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if str(order.customer_id) != str(customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to request a replacement for this order",
        )

    # Verify item belongs to order
    item_result = await db.execute(
        select(OrderItem).where(
            OrderItem.id == item_uuid,
            OrderItem.order_id == order_uuid,
        )
    )
    item = item_result.scalar_one_or_none()

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order item not found or does not belong to this order",
        )

    idempotency_key = f"{conversation_id}:replacement:{order_id}:{item_id}"

    # Check for existing replacement with same idempotency key
    existing_result = await db.execute(
        select(Replacement).where(Replacement.idempotency_key == idempotency_key)
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        output = {
            "replacement_id": str(existing.id),
            "status": existing.status,
            "requires_approval": True,
            "approval_id": None,
            "message": "Replacement already exists for this conversation (idempotent response).",
        }
        latency = int((time.monotonic() - start) * 1000)
        await _log_tool_call(db, conversation_id, "create_replacement", args, output, latency)
        return output

    replacement = Replacement(
        order_id=order_id,
        item_id=item_id,
        reason=reason,
        status="pending",
        idempotency_key=idempotency_key,
    )
    db.add(replacement)
    await db.flush()

    # Replacements always require approval (medium risk)
    approval = Approval(
        conversation_id=conversation_id,
        action="create_replacement",
        args_json={
            "order_id": order_id,
            "item_id": item_id,
            "reason": reason,
            "item_name": item.name,
            "item_sku": item.sku,
        },
        reasoning=f"Customer requested replacement for '{item.name}' (SKU: {item.sku}). Reason: {reason}. Requires staff verification.",
        status="pending",
    )
    db.add(approval)
    await db.flush()

    output = {
        "replacement_id": str(replacement.id),
        "status": "pending",
        "requires_approval": True,
        "approval_id": str(approval.id),
        "item_name": item.name,
        "message": f"Replacement request for '{item.name}' submitted. A staff member will review and approve it shortly.",
    }

    latency = int((time.monotonic() - start) * 1000)
    await _log_tool_call(db, conversation_id, "create_replacement", args, output, latency)
    return output
