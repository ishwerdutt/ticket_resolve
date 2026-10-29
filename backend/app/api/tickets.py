"""Ticket endpoints for customers and staff."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_customer, get_current_staff
from app.database import get_db
from app.models.db import Ticket
from app.models.schemas import TicketOut

router = APIRouter(tags=["tickets"])


@router.get("/tickets", response_model=list[TicketOut])
async def list_customer_tickets(
    current_customer: dict = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> list[TicketOut]:
    """List all tickets for the authenticated customer."""
    customer_id = UUID(current_customer["customer_id"])
    result = await db.execute(
        select(Ticket)
        .where(Ticket.customer_id == customer_id)
        .order_by(Ticket.created_at.desc())
    )
    return result.scalars().all()


@router.get("/tickets/{ticket_id}", response_model=TicketOut)
async def get_customer_ticket(
    ticket_id: str,
    current_customer: dict = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> TicketOut:
    """Get a specific ticket for the authenticated customer."""
    try:
        t_uuid = UUID(ticket_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid ticket ID format",
        )

    customer_id = UUID(current_customer["customer_id"])
    result = await db.execute(
        select(Ticket).where(Ticket.id == t_uuid, Ticket.customer_id == customer_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )
    return ticket


@router.get("/admin/tickets", response_model=list[TicketOut])
async def list_all_tickets(
    status_filter: Optional[str] = Query(None, alias="status"),
    priority_filter: Optional[str] = Query(None, alias="priority"),
    current_staff: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
) -> list[TicketOut]:
    """Staff only: list all tickets across all customers with optional filters."""
    query = select(Ticket).order_by(Ticket.created_at.desc())

    if status_filter:
        query = query.where(Ticket.status == status_filter)
    if priority_filter:
        query = query.where(Ticket.priority == priority_filter)

    result = await db.execute(query)
    return result.scalars().all()
