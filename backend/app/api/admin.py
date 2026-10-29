"""Admin API endpoints — metrics and analytics."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_staff
from app.database import get_db
from app.models.db import Approval, Conversation, Refund, ToolCall
from app.models.schemas import MetricsOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/metrics", response_model=MetricsOut)
async def get_metrics(
    current_staff: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
) -> MetricsOut:
    """Return system-wide metrics for the admin dashboard."""

    # Total conversations
    total_result = await db.execute(select(func.count()).select_from(Conversation))
    total_conversations = total_result.scalar() or 0

    # Resolved conversations
    resolved_result = await db.execute(
        select(func.count()).where(Conversation.state == "RESOLVED")
    )
    resolved_count = resolved_result.scalar() or 0

    # Escalated conversations
    escalated_result = await db.execute(
        select(func.count()).where(Conversation.state == "ESCALATED")
    )
    escalated_count = escalated_result.scalar() or 0

    # Pending approvals
    pending_result = await db.execute(
        select(func.count()).where(Approval.status == "pending")
    )
    pending_approvals_count = pending_result.scalar() or 0

    # Total refunds amount (approved + processed)
    refund_result = await db.execute(
        select(func.coalesce(func.sum(Refund.amount), 0)).where(
            Refund.status.in_(["approved", "processed"])
        )
    )
    total_refunds_amount = float(refund_result.scalar() or 0)

    # Average tool calls per conversation
    subq = (
        select(func.count(ToolCall.id).label("cnt"))
        .select_from(ToolCall)
        .group_by(ToolCall.conversation_id)
        .subquery()
    )
    avg_result = await db.execute(select(func.coalesce(func.avg(subq.c.cnt), 0.0)))
    avg_tool_calls = float(avg_result.scalar() or 0.0)

    return MetricsOut(
        total_conversations=total_conversations,
        resolved_count=resolved_count,
        escalated_count=escalated_count,
        pending_approvals_count=pending_approvals_count,
        total_refunds_amount=total_refunds_amount,
        avg_tool_calls_per_conversation=round(avg_tool_calls, 2),
    )
