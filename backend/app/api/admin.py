"""Admin API endpoints — metrics, analytics, and real-time activity stream."""
from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_staff
from app.database import get_db
from app.models.db import Approval, Conversation, Customer, Message, Refund, Ticket, ToolCall
from app.models.schemas import ActivityEvent, MetricsOut

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


@router.get("/activity", response_model=List[ActivityEvent])
async def get_activity(
    limit: int = Query(30, ge=1, le=100),
    current_staff: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
) -> List[ActivityEvent]:
    """Return chronological event stream of tool calls, approvals, tickets, and messages."""
    events: List[ActivityEvent] = []

    # 1. Fetch recent tool calls with customer info
    tc_res = await db.execute(
        select(ToolCall, Conversation.customer_id, Customer.name.label("customer_name"))
        .join(Conversation, ToolCall.conversation_id == Conversation.id, isouter=True)
        .join(Customer, Conversation.customer_id == Customer.id, isouter=True)
        .order_by(ToolCall.created_at.desc())
        .limit(limit)
    )
    for row in tc_res.all():
        tc = row[0]
        cust_name = row[2] or "Customer"
        tool_desc = ""
        args = tc.args_json or {}
        if tc.tool == "get_order":
            tool_desc = f"Fetched order details (Order #{str(args.get('order_id', ''))[:8]})"
        elif tc.tool == "track_shipment":
            tool_desc = f"Tracked shipment for Order #{str(args.get('order_id', ''))[:8]}"
        elif tc.tool == "search_policy":
            tool_desc = f"Searched policies: \"{args.get('query', '')[:40]}\""
        elif tc.tool == "create_refund":
            tool_desc = f"Created refund for ₹{args.get('amount', 0):,.2f} ({args.get('reason', '')})"
        elif tc.tool == "update_address":
            tool_desc = f"Updated shipping address to {args.get('new_address', {}).get('city', '')}"
        elif tc.tool == "check_refund_eligibility":
            tool_desc = "Checked refund policy window eligibility"
        elif tc.tool == "create_ticket":
            tool_desc = f"Created support ticket: {args.get('summary', '')[:40]}"
        else:
            tool_desc = f"Executed {tc.tool}"

        events.append(
            ActivityEvent(
                id=f"tc_{tc.id}",
                type="tool_call",
                title=f"Tool Executed: {tc.tool}",
                description=tool_desc,
                customer_name=cust_name,
                conversation_id=str(tc.conversation_id),
                created_at=tc.created_at,
                latency_ms=tc.latency_ms,
                details={"args": tc.args_json, "result": tc.result_json},
            )
        )

    # 2. Fetch recent approvals
    appr_res = await db.execute(
        select(Approval, Conversation.customer_id, Customer.name.label("customer_name"))
        .join(Conversation, Approval.conversation_id == Conversation.id, isouter=True)
        .join(Customer, Conversation.customer_id == Customer.id, isouter=True)
        .order_by(Approval.created_at.desc())
        .limit(limit)
    )
    for row in appr_res.all():
        appr = row[0]
        cust_name = row[2] or "Customer"
        events.append(
            ActivityEvent(
                id=f"appr_{appr.id}",
                type="approval",
                title=f"Approval: {appr.action.replace('_', ' ').title()}",
                description=f"Status: {appr.status.upper()} · {appr.reasoning or 'Requires staff review'}",
                customer_name=cust_name,
                conversation_id=str(appr.conversation_id),
                created_at=appr.created_at,
                status=appr.status,
                details=appr.args_json,
            )
        )

    # 3. Fetch recent tickets
    tick_res = await db.execute(
        select(Ticket, Customer.name.label("customer_name"))
        .join(Customer, Ticket.customer_id == Customer.id, isouter=True)
        .order_by(Ticket.created_at.desc())
        .limit(limit)
    )
    for row in tick_res.all():
        tick = row[0]
        cust_name = row[1] or "Customer"
        events.append(
            ActivityEvent(
                id=f"tick_{tick.id}",
                type="ticket",
                title=f"Ticket #{str(tick.id)[:8]} ({tick.priority.upper()})",
                description=tick.summary,
                customer_name=cust_name,
                created_at=tick.created_at,
                status=tick.status,
                details={"priority": tick.priority, "status": tick.status},
            )
        )

    # 4. Fetch recent messages
    msg_res = await db.execute(
        select(Message, Conversation.customer_id, Customer.name.label("customer_name"))
        .join(Conversation, Message.conversation_id == Conversation.id, isouter=True)
        .join(Customer, Conversation.customer_id == Customer.id, isouter=True)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    for row in msg_res.all():
        msg = row[0]
        cust_name = row[2] or "Customer"
        title = f"{cust_name} (User)" if msg.role == "user" else "Tara (ThreadNest AI)"
        events.append(
            ActivityEvent(
                id=f"msg_{msg.id}",
                type="message",
                title=title,
                description=msg.content[:140] + ("..." if len(msg.content) > 140 else ""),
                customer_name=cust_name,
                conversation_id=str(msg.conversation_id),
                created_at=msg.created_at,
                status=msg.role,
                details={"role": msg.role, "full_content": msg.content},
            )
        )

    # Sort all events chronologically descending and limit
    events.sort(key=lambda e: e.created_at, reverse=True)
    return events[:limit]

