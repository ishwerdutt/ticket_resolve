"""Unit tests for Tickets API endpoints."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.tickets import get_customer_ticket, list_all_tickets, list_customer_tickets
from app.models.db import Ticket


def make_uuid() -> str:
    return str(uuid.uuid4())


def make_mock_ticket(customer_id: str, summary: str = "Test issue"):
    ticket = MagicMock(spec=Ticket)
    ticket.id = uuid.uuid4()
    ticket.customer_id = uuid.UUID(customer_id)
    ticket.status = "open"
    ticket.priority = "medium"
    ticket.summary = summary
    ticket.assigned_to = None
    ticket.created_at = datetime.now(timezone.utc)
    return ticket


@pytest.mark.asyncio
async def test_list_customer_tickets():
    cid = make_uuid()
    t = make_mock_ticket(cid)

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [t]
    db.execute = AsyncMock(return_value=result_mock)

    tickets = await list_customer_tickets(
        current_customer={"customer_id": cid, "email": "test@example.com"},
        db=db,
    )
    assert len(tickets) == 1
    assert tickets[0].summary == "Test issue"


@pytest.mark.asyncio
async def test_get_customer_ticket_not_found():
    cid = make_uuid()
    tid = make_uuid()

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result_mock)

    with pytest.raises(HTTPException) as exc:
        await get_customer_ticket(
            ticket_id=tid,
            current_customer={"customer_id": cid, "email": "test@example.com"},
            db=db,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_metrics_endpoint():
    from app.api.admin import get_metrics

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 5
    db.execute = AsyncMock(return_value=mock_result)

    metrics = await get_metrics(
        current_staff={"staff_id": make_uuid(), "email": "admin@threadnest.com", "role": "admin"},
        db=db,
    )
    assert metrics.total_conversations == 5
    assert metrics.resolved_count == 5


@pytest.mark.asyncio
async def test_get_activity_endpoint():
    from app.api.admin import get_activity

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    events = await get_activity(
        limit=10,
        current_staff={"staff_id": make_uuid(), "email": "reviewer@threadnest.com", "role": "reviewer"},
        db=db,
    )
    assert isinstance(events, list)
    assert len(events) == 0


