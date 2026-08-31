import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.roles import ROLE_ORDER, ROLES
from app.agents.service import get_agent, seed_project_agents
from app.api.deps import get_current_user
from app.core.config import Settings, get_settings
from app.cost.engine import cost_engine
from app.database.session import async_session_maker, get_db
from app.events.bus import event_bus
from app.models.agent import Agent
from app.models.agent_run import AgentRun
from app.models.project import Project
from app.models.user import User
from app.orchestrator.runner import AgentRunner
from app.providers.liara import LiaraProvider
from app.schemas.agent import AgentModelUpdate, AgentResponse, AgentRunRequest, AgentRunResponse
from app.tools.gateway import tool_gateway
from app.tools.model_tools import validate_model_choice

router = APIRouter(prefix="/projects", tags=["agents"])

_background_tasks: set[asyncio.Task] = set()


async def _require_agent(db: AsyncSession, project_id: str, role: str, settings: Settings) -> Agent:
    """Fetch a role's agent, backfilling the roster first so projects created before a role
    existed still work."""
    if role not in ROLES:
        raise HTTPException(status_code=404, detail=f"Unknown role '{role}'")
    agent = await get_agent(db, project_id, role)
    if agent is None:
        await seed_project_agents(db, project_id, settings)
        agent = await get_agent(db, project_id, role)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"No '{role}' agent on this project")
    return agent


@router.post("/{project_id}/agents/{role}/run", response_model=AgentRunResponse)
async def run_agent(
    project_id: str,
    role: str,
    payload: AgentRunRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _current_user: User = Depends(get_current_user),
) -> AgentRun:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    agent = await _require_agent(db, project_id, role, settings)

    run = AgentRun(
        agent_id=agent.id,
        project_id=project.id,
        status="queued",
        input_message=payload.message,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    provider = LiaraProvider(
        api_key=settings.liara_api_key,
        base_url=settings.liara_base_url,
        timeout=settings.provider_timeout_seconds,
    )
    runner = AgentRunner(async_session_maker, provider, tool_gateway, event_bus, cost_engine, settings)
    task = asyncio.create_task(runner.run(run.id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return run


@router.get("/{project_id}/agents/runs", response_model=list[AgentRunResponse])
async def list_agent_runs(
    project_id: str, db: AsyncSession = Depends(get_db), _current_user: User = Depends(get_current_user)
) -> list[AgentRun]:
    result = await db.execute(
        select(AgentRun).where(AgentRun.project_id == project_id).order_by(AgentRun.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{project_id}/agents", response_model=list[AgentResponse])
async def list_project_agents(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _current_user: User = Depends(get_current_user),
) -> list[AgentResponse]:
    agents = await seed_project_agents(db, project_id, settings)
    order = {name: i for i, name in enumerate(ROLE_ORDER)}
    agents.sort(key=lambda a: order.get(a.role, len(order)))
    return [
        AgentResponse(
            **{c.name: getattr(agent, c.name) for c in Agent.__table__.columns if c.name in AgentResponse.model_fields},
            summary=ROLES[agent.role].summary if agent.role in ROLES else "",
        )
        for agent in agents
    ]


@router.put("/{project_id}/agents/{role}/model", response_model=AgentResponse)
async def set_agent_model(
    project_id: str,
    role: str,
    payload: AgentModelUpdate,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _current_user: User = Depends(get_current_user),
) -> Agent:
    """Human-driven counterpart to the agent's own model.switch tool: pick the model manually.
    Both go through the same validation so the allow-list is enforced either way."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    agent = await _require_agent(db, project_id, role, settings)

    error = await validate_model_choice(db, agent=agent, model_id=payload.model_id)
    if error:
        raise HTTPException(status_code=400, detail=error)

    agent.selected_model_id = payload.model_id
    await db.commit()
    await db.refresh(agent)
    return agent
