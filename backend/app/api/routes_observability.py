from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.agent import Agent
from app.models.agent_run import AgentRun
from app.models.model_request import ModelRequest
from app.models.system_event import SystemEvent
from app.models.user import User

router = APIRouter(tags=["observability"])

# Actual cost when the provider reported one, our estimate otherwise - the same rule the cost
# engine records by, so every view of spend agrees with every other.
SPEND = func.coalesce(ModelRequest.actual_cost, ModelRequest.estimated_cost)


class EventResponse(BaseModel):
    id: str
    project_id: str | None
    agent_run_id: str | None
    event_type: str
    payload: dict
    created_at: datetime

    class Config:
        from_attributes = True


class CostBucket(BaseModel):
    key: str
    requests: int
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost_usd: float


class CostSummary(BaseModel):
    total_cost_usd: float
    total_requests: int
    total_input_tokens: int
    total_output_tokens: int
    total_cached_tokens: int
    by_model: list[CostBucket]
    by_role: list[CostBucket]
    by_project: list[CostBucket]


@router.get("/events", response_model=list[EventResponse])
async def list_events(
    project_id: str | None = None,
    event_type: str | None = None,
    limit: int = Query(100, le=500),
    before: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[SystemEvent]:
    query = select(SystemEvent).order_by(SystemEvent.created_at.desc()).limit(limit)
    if project_id:
        query = query.where(SystemEvent.project_id == project_id)
    if event_type:
        query = query.where(SystemEvent.event_type == event_type)
    if before:
        query = query.where(SystemEvent.created_at < before)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/costs", response_model=CostSummary)
async def cost_summary(
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> CostSummary:
    """Spend broken down the ways you would actually want to act on it: which model, which
    role, which project."""

    def scoped(query):
        if project_id:
            return query.join(AgentRun, AgentRun.id == ModelRequest.agent_run_id).where(
                AgentRun.project_id == project_id
            )
        return query

    totals = (
        await db.execute(
            scoped(
                select(
                    func.count(ModelRequest.id),
                    func.coalesce(func.sum(cast(SPEND, Float)), 0.0),
                    func.coalesce(func.sum(ModelRequest.input_tokens), 0),
                    func.coalesce(func.sum(ModelRequest.output_tokens), 0),
                    func.coalesce(func.sum(ModelRequest.cached_tokens), 0),
                )
            )
        )
    ).one()

    by_model = await _bucket(db, ModelRequest.model_id, project_id)
    by_role = await _bucket(db, Agent.role, project_id, join_agent=True)
    by_project = await _bucket(db, AgentRun.project_id, project_id, join_run=True)

    return CostSummary(
        total_requests=totals[0],
        total_cost_usd=round(float(totals[1]), 6),
        total_input_tokens=totals[2],
        total_output_tokens=totals[3],
        total_cached_tokens=totals[4],
        by_model=by_model,
        by_role=by_role,
        by_project=by_project,
    )


async def _bucket(
    db: AsyncSession, column, project_id: str | None, *, join_agent: bool = False, join_run: bool = False
) -> list[CostBucket]:
    query = select(
        column,
        func.count(ModelRequest.id),
        func.coalesce(func.sum(ModelRequest.input_tokens), 0),
        func.coalesce(func.sum(ModelRequest.output_tokens), 0),
        func.coalesce(func.sum(ModelRequest.cached_tokens), 0),
        func.coalesce(func.sum(cast(SPEND, Float)), 0.0),
    )
    if join_agent or join_run or project_id:
        query = query.join(AgentRun, AgentRun.id == ModelRequest.agent_run_id)
    if join_agent:
        query = query.join(Agent, Agent.id == AgentRun.agent_id)
    if project_id:
        query = query.where(AgentRun.project_id == project_id)

    result = await db.execute(query.group_by(column).order_by(func.sum(cast(SPEND, Float)).desc()))
    return [
        CostBucket(
            key=str(row[0]),
            requests=row[1],
            input_tokens=row[2],
            output_tokens=row[3],
            cached_tokens=row[4],
            cost_usd=round(float(row[5]), 6),
        )
        for row in result.all()
    ]
