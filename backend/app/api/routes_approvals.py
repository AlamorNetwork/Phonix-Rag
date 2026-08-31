from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.approvals.service import ApprovalEngine, approval_engine
from app.database.session import get_db
from app.models.approval import Approval
from app.models.user import User
from app.schemas.approval import ApprovalDecisionRequest, ApprovalResponse

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalResponse])
async def list_approvals(
    status_filter: str | None = None,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[Approval]:
    query = select(Approval).order_by(Approval.created_at.desc())
    if status_filter:
        query = query.where(Approval.status == status_filter)
    result = await db.execute(query)
    return list(result.scalars().all())


async def _decide(
    approval_id: str, decision: str, payload: ApprovalDecisionRequest, db: AsyncSession, current_user: User
) -> Approval:
    approval = await db.get(Approval, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail=f"Approval already {approval.status}")

    ApprovalEngine.mark_decided(approval, decision=decision, decided_by=current_user.email)
    await db.commit()
    await db.refresh(approval)

    resolved = approval_engine.resolve(approval.id, decision)
    if not resolved:
        raise HTTPException(
            status_code=409,
            detail="No agent run is currently waiting on this approval (server may have restarted)",
        )
    return approval


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
async def approve(
    approval_id: str,
    payload: ApprovalDecisionRequest = ApprovalDecisionRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Approval:
    return await _decide(approval_id, "approved", payload, db, current_user)


@router.post("/{approval_id}/deny", response_model=ApprovalResponse)
async def deny(
    approval_id: str,
    payload: ApprovalDecisionRequest = ApprovalDecisionRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Approval:
    return await _decide(approval_id, "denied", payload, db, current_user)
