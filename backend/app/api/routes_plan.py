from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import async_session_maker, get_db
from app.events.bus import event_bus
from app.models.project import Project, ProjectStatus
from app.models.project_task import ProjectTask, TaskStatus
from app.models.user import User
from app.schemas.task import PlanResponse, TaskResponse

router = APIRouter(prefix="/projects", tags=["plan"])


async def _load_plan(db: AsyncSession, project_id: str) -> PlanResponse:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = await db.execute(
        select(ProjectTask).where(ProjectTask.project_id == project_id).order_by(ProjectTask.order_index)
    )
    tasks = list(result.scalars().all())
    total = sum(t.estimated_cost_usd or 0.0 for t in tasks)
    return PlanResponse(
        project_id=project_id,
        project_status=project.status,
        tasks=[TaskResponse.model_validate(t) for t in tasks],
        estimated_total_usd=round(total, 6) if total else None,
    )


@router.get("/{project_id}/plan", response_model=PlanResponse)
async def get_plan(
    project_id: str, db: AsyncSession = Depends(get_db), _current_user: User = Depends(get_current_user)
) -> PlanResponse:
    return await _load_plan(db, project_id)


@router.post("/{project_id}/plan/approve", response_model=PlanResponse)
async def approve_plan(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PlanResponse:
    """The gate the whole plan step exists for: until a human calls this, the tasks the Manager
    wrote are inert rows and no agent will act on them."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.status != ProjectStatus.PLAN_PROPOSED:
        raise HTTPException(
            status_code=409,
            detail=f"No plan is awaiting approval (project is '{project.status}')",
        )

    result = await db.execute(select(ProjectTask).where(ProjectTask.project_id == project_id))
    if not list(result.scalars().all()):
        raise HTTPException(status_code=409, detail="The proposed plan has no tasks")

    project.status = ProjectStatus.EXECUTING
    await db.commit()

    await event_bus.publish(
        async_session_maker,
        project_id=project_id,
        event_type="plan.approved",
        payload={"approved_by": current_user.email},
    )
    return await _load_plan(db, project_id)


@router.post("/{project_id}/plan/reject", response_model=PlanResponse)
async def reject_plan(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PlanResponse:
    """Send the plan back. The tasks stay so the Manager can see what it proposed, but the
    project returns to planning and nothing can execute."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.status != ProjectStatus.PLAN_PROPOSED:
        raise HTTPException(
            status_code=409,
            detail=f"No plan is awaiting approval (project is '{project.status}')",
        )

    project.status = ProjectStatus.PLANNING
    await db.commit()

    await event_bus.publish(
        async_session_maker,
        project_id=project_id,
        event_type="plan.rejected",
        payload={"rejected_by": current_user.email},
    )
    return await _load_plan(db, project_id)
