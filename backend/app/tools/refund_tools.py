"""Refund-related tool functions."""
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.db import Approval, Order, Refund, ToolCall


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


async def check_refund_eligibility(
    order_id: str,
    reason: str,
    customer_id: str,
    db: AsyncSession,
    conversation_id: str = "unknown",
) -> dict:
    """
    Check if an order is eligible for a refund.

    Rules:
    1. Order must belong to the customer.
    2. Order status must be 'delivered'.
    3. delivered_at must be within 30 days.
    """
    start = time.monotonic()
    args = {"order_id": order_id, "reason": reason}

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
            detail="You do not have permission to check refund eligibility for this order",
        )

    if order.status != "delivered":
        output = {
            "eligible": False,
            "max_amount": 0.0,
            "rule_cited": "REFUND_POLICY_001",
            "reason": f"Order is not delivered yet (current status: '{order.status}'). Refunds are only available for delivered orders.",
        }
    elif order.delivered_at is None:
        output = {
            "eligible": False,
            "max_amount": 0.0,
            "rule_cited": "REFUND_POLICY_001",
            "reason": "Delivery date not recorded. Please contact support.",
        }
    else:
        now = datetime.now(timezone.utc)
        # Make delivered_at timezone-aware if it isn't
        delivered_at = order.delivered_at
        if delivered_at.tzinfo is None:
            delivered_at = delivered_at.replace(tzinfo=timezone.utc)

        days_since_delivery = (now - delivered_at).days

        if days_since_delivery > 30:
            output = {
                "eligible": False,
                "max_amount": 0.0,
                "rule_cited": "REFUND_POLICY_002",
                "reason": (
                    f"Refund window has expired. Order was delivered {days_since_delivery} days ago. "
                    "ThreadNest's refund policy allows refunds within 30 days of delivery."
                ),
            }
        else:
            output = {
                "eligible": True,
                "max_amount": float(order.total),
                "rule_cited": "REFUND_POLICY_003",
                "reason": (
                    f"Order is eligible for a refund. Delivered {days_since_delivery} day(s) ago. "
                    f"Maximum refund amount: ₹{float(order.total):.2f}."
                ),
            }

    latency = int((time.monotonic() - start) * 1000)
    await _log_tool_call(db, conversation_id, "check_refund_eligibility", args, output, latency)
    return output


async def create_refund(
    order_id: str,
    amount: float,
    reason: str,
    customer_id: str,
    conversation_id: str,
    db: AsyncSession,
) -> dict:
    """
    Create a refund for a delivered order.

    - If amount <= REFUND_AUTO_APPROVE_LIMIT: auto-approve.
    - Else: create pending refund + approval request.
    - Idempotency key prevents duplicate refunds per conversation.
    """
    start = time.monotonic()
    args = {"order_id": order_id, "amount": amount, "reason": reason}

    try:
        order_uuid = UUID(str(order_id).strip())
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid order ID format '{order_id}'. Order IDs must be valid UUIDs.",
        )

    idempotency_key = f"{conversation_id}:refund:{order_id}"

    # Check for existing refund with same idempotency key
    existing = await db.execute(
        select(Refund).where(Refund.idempotency_key == idempotency_key)
    )
    existing_refund = existing.scalar_one_or_none()
    if existing_refund:
        output = {
            "refund_id": str(existing_refund.id),
            "status": existing_refund.status,
            "requires_approval": existing_refund.status == "pending",
            "approval_id": None,
            "message": "Refund already exists for this conversation (idempotent response).",
        }
        latency = int((time.monotonic() - start) * 1000)
        await _log_tool_call(db, conversation_id, "create_refund", args, output, latency)
        return output

    auto_approve = amount <= settings.REFUND_AUTO_APPROVE_LIMIT
    refund_status = "approved" if auto_approve else "pending"

    refund = Refund(
        order_id=order_id,
        amount=amount,
        reason=reason,
        status=refund_status,
        created_by=customer_id,
        idempotency_key=idempotency_key,
    )
    db.add(refund)
    await db.flush()  # populate refund.id

    approval_id: Optional[str] = None
    if not auto_approve:
        approval = Approval(
            conversation_id=conversation_id,
            action="create_refund",
            args_json={"order_id": order_id, "amount": amount, "reason": reason},
            reasoning=f"Refund amount ₹{amount:.2f} exceeds auto-approve limit of ₹{settings.REFUND_AUTO_APPROVE_LIMIT:.2f}. Requires staff review.",
            status="pending",
        )
        db.add(approval)
        await db.flush()
        approval_id = str(approval.id)

    output = {
        "refund_id": str(refund.id),
        "status": refund_status,
        "amount": amount,
        "requires_approval": not auto_approve,
        "approval_id": approval_id,
        "message": (
            f"Refund of ₹{amount:.2f} {'auto-approved' if auto_approve else 'submitted for staff review'}."
        ),
    }

    latency = int((time.monotonic() - start) * 1000)
    await _log_tool_call(db, conversation_id, "create_refund", args, output, latency)
    return output
