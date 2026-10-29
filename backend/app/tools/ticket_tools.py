"""Ticket creation tool."""
import time
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Conversation, Ticket, ToolCall


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


async def create_ticket(
    customer_id: str,
    summary: str,
    priority: str,
    conversation_id: str,
    db: AsyncSession,
) -> dict:
    """
    Create a support ticket and link it to the current conversation.

    Returns the ticket ID and initial status.
    """
    start = time.monotonic()
    args = {"customer_id": customer_id, "summary": summary, "priority": priority}

    ticket = Ticket(
        customer_id=customer_id,
        summary=summary,
        priority=priority,
        status="open",
    )
    db.add(ticket)
    await db.flush()

    # Link ticket to conversation
    from sqlalchemy import select
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = conv_result.scalar_one_or_none()
    if conv:
        conv.ticket_id = ticket.id
        conv.state = "ESCALATED"

    output = {
        "ticket_id": str(ticket.id),
        "status": "open",
        "priority": priority,
        "summary": summary,
        "message": f"Support ticket created (priority: {priority}). A staff member will review your case shortly.",
    }

    latency = int((time.monotonic() - start) * 1000)
    await _log_tool_call(db, conversation_id, "create_ticket", args, output, latency)
    return output
