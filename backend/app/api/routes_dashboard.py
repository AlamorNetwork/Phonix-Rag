from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.agent import Agent
from app.models.agent_run import AgentRun
from app.models.approval import Approval
from app.models.model_request import ModelRequest
from app.models.project import Project
from app.models.project_task import ProjectTask, TaskStatus
from app.models.system_event import SystemEvent
from app.models.user import User

router = APIRouter(tags=["dashboard"])

SPEND = func.coalesce(ModelRequest.actual_cost, ModelRequest.estimated_cost)
ACTIVE_RUN_STATES = ("queued", "running")


class PendingApproval(BaseModel):
    id: str
    risk_level: str
    reason: str
    agent_run_id: str
    project_id: str | None
    project_name: str | None
    created_at: datetime


class ActiveRun(BaseModel):
    id: str
    project_id: str
    project_name: str
    role: str
    model_id: str | None
    status: str
    input_message: str
    started_at: datetime | None


class ProjectCard(BaseModel):
    id: str
    name: str
    idea: str
    status: str
    tasks_total: int
    tasks_done: int
    tasks_blocked: int
    cost_usd: float
    created_at: datetime


class RecentEvent(BaseModel):
    id: str
    event_type: str
    project_id: str | None
    payload: dict
    created_at: datetime


class DashboardResponse(BaseModel):
    # Things wanting a human come first: this is the gate the whole product is built around.
    pending_approvals: list[PendingApproval]
    active_runs: list[ActiveRun]
    projects_total: int
    projects_executing: int
    tasks_total: int
    tasks_done: int
    tasks_blocked: int
    cost_total_usd: float
    cost_today_usd: float
    tokens_in: int
    tokens_out: int
    projects: list[ProjectCard]
    recent_events: list[RecentEvent]


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> DashboardResponse:
    """Everything the command centre shows, in one round trip."""
    project_names = {
        p.id: p.name for p in (await db.execute(select(Project))).scalars().all()
    }

    approvals = (
        await db.execute(
            select(Approval, AgentRun.project_id)
            .join(AgentRun, AgentRun.id == Approval.agent_run_id)
            .where(Approval.status == "pending")
            .order_by(Approval.created_at.desc())
            .limit(20)
        )
    ).all()

    runs = (
        await db.execute(
            select(AgentRun, Agent.role, Agent.selected_model_id, Project.name)
            .join(Agent, Agent.id == AgentRun.agent_id)
            .join(Project, Project.id == AgentRun.project_id)
            .where(AgentRun.status.in_(ACTIVE_RUN_STATES))
            .order_by(AgentRun.created_at.desc())
            .limit(20)
        )
    ).all()

    task_counts = dict(
        (
            await db.execute(select(ProjectTask.status, func.count()).group_by(ProjectTask.status))
        ).all()
    )

    cost_total = float(
        (await db.execute(select(func.coalesce(func.sum(cast(SPEND, Float)), 0.0)))).scalar_one()
    )
    midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    cost_today = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(cast(SPEND, Float)), 0.0)).where(
                    ModelRequest.created_at >= midnight
                )
            )
        ).scalar_one()
    )
    tokens = (
        await db.execute(
            select(
                func.coalesce(func.sum(ModelRequest.input_tokens), 0),
                func.coalesce(func.sum(ModelRequest.output_tokens), 0),
            )
        )
    ).one()

    per_project_tasks = {
        (row[0], row[1]): row[2]
        for row in (
            await db.execute(
                select(ProjectTask.project_id, ProjectTask.status, func.count()).group_by(
                    ProjectTask.project_id, ProjectTask.status
                )
            )
        ).all()
    }
    per_project_cost = {
        row[0]: float(row[1])
        for row in (
            await db.execute(
                select(AgentRun.project_id, func.coalesce(func.sum(cast(SPEND, Float)), 0.0))
                .join(ModelRequest, ModelRequest.agent_run_id == AgentRun.id)
                .group_by(AgentRun.project_id)
            )
        ).all()
    }

    recent_projects = (
        await db.execute(select(Project).order_by(Project.created_at.desc()).limit(8))
    ).scalars().all()

    def task_count(project_id: str, status: str) -> int:
        return per_project_tasks.get((project_id, status), 0)

    projects = [
        ProjectCard(
            id=p.id,
            name=p.name,
            idea=p.idea,
            status=p.status,
            tasks_total=sum(v for (pid, _), v in per_project_tasks.items() if pid == p.id),
            tasks_done=task_count(p.id, TaskStatus.DONE),
            tasks_blocked=task_count(p.id, TaskStatus.BLOCKED),
            cost_usd=round(per_project_cost.get(p.id, 0.0), 6),
            created_at=p.created_at,
        )
        for p in recent_projects
    ]

    events = (
        await db.execute(select(SystemEvent).order_by(SystemEvent.created_at.desc()).limit(25))
    ).scalars().all()

    return DashboardResponse(
        pending_approvals=[
            PendingApproval(
                id=a.id,
                risk_level=a.risk_level,
                reason=a.reason,
                agent_run_id=a.agent_run_id,
                project_id=pid,
                project_name=project_names.get(pid),
                created_at=a.created_at,
            )
            for a, pid in approvals
        ],
        active_runs=[
            ActiveRun(
                id=r.id,
                project_id=r.project_id,
                project_name=name,
                role=role,
                model_id=model_id,
                status=r.status,
                input_message=r.input_message,
                started_at=r.started_at,
            )
            for r, role, model_id, name in runs
        ],
        projects_total=len(project_names),
        projects_executing=sum(1 for p in recent_projects if p.status == "executing"),
        tasks_total=sum(task_counts.values()),
        tasks_done=task_counts.get(TaskStatus.DONE, 0),
        tasks_blocked=task_counts.get(TaskStatus.BLOCKED, 0),
        cost_total_usd=round(cost_total, 6),
        cost_today_usd=round(cost_today, 6),
        tokens_in=tokens[0],
        tokens_out=tokens[1],
        projects=projects,
        recent_events=[
            RecentEvent(
                id=e.id,
                event_type=e.event_type,
                project_id=e.project_id,
                payload=e.payload,
                created_at=e.created_at,
            )
            for e in events
        ],
    )
