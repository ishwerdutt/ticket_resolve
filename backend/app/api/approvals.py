"""Approvals API endpoints — staff-facing review queue."""
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_staff
from app.database import get_db
from app.models.db import Approval, Refund
from app.models.schemas import ApprovalDecision, ApprovalOut

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=List[ApprovalOut])
async def list_approvals(
    current_staff: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
) -> List[ApprovalOut]:
    """List all pending approvals with conversation context."""
    result = await db.execute(
        select(Approval)
        .where(Approval.status == "pending")
        .order_by(Approval.created_at.desc())
    )
    approvals = result.scalars().all()
    return [ApprovalOut.model_validate(a) for a in approvals]


@router.get("/{approval_id}", response_model=ApprovalOut)
async def get_approval(
    approval_id: str,
    current_staff: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
) -> ApprovalOut:
    """Get a single approval by ID."""
    result = await db.execute(
        select(Approval).where(Approval.id == approval_id)
    )
    approval = result.scalar_one_or_none()

    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval not found",
        )

    return ApprovalOut.model_validate(approval)


@router.post("/{approval_id}/decide", response_model=ApprovalOut)
async def decide_approval(
    approval_id: str,
    decision: ApprovalDecision,
    current_staff: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
) -> ApprovalOut:
    """
    Approve or reject a pending approval.

    On approve:
    - For refund actions: update the associated refund status to 'approved'.
    - For replacement actions: update replacement status to 'approved'.
    On reject:
    - Update approval and related record to 'rejected'.
    """
    result = await db.execute(
        select(Approval).where(Approval.id == approval_id)
    )
    approval = result.scalar_one_or_none()

    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval not found",
        )

    if approval.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Approval has already been {approval.status}",
        )

    staff_id = current_staff["staff_id"]
    new_status = "approved" if decision.action == "approve" else "rejected"

    # Update approval
    approval.status = new_status
    approval.reviewer_id = staff_id
    approval.decided_at = datetime.now(timezone.utc)
    if decision.reason:
        approval.reasoning = (approval.reasoning or "") + f"\nReviewer note: {decision.reason}"

    # Execute the action downstream
    if approval.action == "create_refund":
        await _handle_refund_decision(approval, new_status, staff_id, db)
    elif approval.action == "create_replacement":
        await _handle_replacement_decision(approval, new_status, db)

    await db.commit()
    await db.refresh(approval)
    return ApprovalOut.model_validate(approval)


async def _handle_refund_decision(
    approval: Approval,
    new_status: str,
    staff_id: str,
    db: AsyncSession,
) -> None:
    """Update refund record based on approval decision."""
    from app.models.db import Refund
    args = approval.args_json or {}
    order_id = args.get("order_id")
    amount = args.get("amount")

    if not order_id:
        return

    result = await db.execute(
        select(Refund).where(
            Refund.order_id == order_id,
            Refund.status == "pending",
        )
    )
    refund = result.scalar_one_or_none()
    if refund:
        refund.status = new_status
        if new_status == "approved":
            refund.approved_by = staff_id


async def _handle_replacement_decision(
    approval: Approval,
    new_status: str,
    db: AsyncSession,
) -> None:
    """Update replacement record based on approval decision."""
    from app.models.db import Replacement
    args = approval.args_json or {}
    order_id = args.get("order_id")
    item_id = args.get("item_id")

    if not order_id or not item_id:
        return

    result = await db.execute(
        select(Replacement).where(
            Replacement.order_id == order_id,
            Replacement.item_id == item_id,
            Replacement.status == "pending",
        )
    )
    replacement = result.scalar_one_or_none()
    if replacement:
        replacement.status = new_status
