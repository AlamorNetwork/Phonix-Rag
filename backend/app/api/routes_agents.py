import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.manager import default_manager_agent_kwargs
from app.api.deps import get_current_user
from app.core.config import Settings, get_settings
from app.cost.engine import cost_engine
from app.database.session import async_session_maker, get_db
from app.events.bus import event_bus
from app.models.agent import Agent
from app.models.agent_run import AgentRun
from app.models.project import Project
from app.models.user import User
from app.models_registry.service import seed_liara_provider
from app.orchestrator.runner import AgentRunner
from app.providers.liara import LiaraProvider
from app.schemas.agent import AgentModelUpdate, AgentResponse, AgentRunRequest, AgentRunResponse
from app.tools.gateway import tool_gateway
from app.tools.model_tools import validate_model_choice

router = APIRouter(prefix="/projects", tags=["agents"])

_background_tasks: set[asyncio.Task] = set()


async def _get_or_create_manager_agent(db: AsyncSession, project: Project, settings: Settings) -> Agent:
    result = await db.execute(
        select(Agent).where(Agent.project_id == project.id, Agent.role == "manager")
    )
    agent = result.scalar_one_or_none()
    if agent:
        return agent

    _, model = await seed_liara_provider(db, settings)
    kwargs = default_manager_agent_kwargs()
    agent = Agent(project_id=project.id, selected_model_id=model.model_id, **kwargs)
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


@router.post("/{project_id}/agents/manager/run", response_model=AgentRunResponse)
async def run_manager_agent(
    project_id: str,
    payload: AgentRunRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _current_user: User = Depends(get_current_user),
) -> AgentRun:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    agent = await _get_or_create_manager_agent(db, project, settings)

    run = AgentRun(
        agent_id=agent.id,
        project_id=project.id,
        status="queued",
        input_message=payload.message,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    provider = LiaraProvider(api_key=settings.liara_api_key, base_url=settings.liara_base_url)
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
    project_id: str, db: AsyncSession = Depends(get_db), _current_user: User = Depends(get_current_user)
) -> list[Agent]:
    result = await db.execute(select(Agent).where(Agent.project_id == project_id))
    return list(result.scalars().all())


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

    agent = await _get_or_create_manager_agent(db, project, settings) if role == "manager" else None
    if agent is None:
        result = await db.execute(select(Agent).where(Agent.project_id == project_id, Agent.role == role))
        agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail=f"No '{role}' agent on this project")

    error = await validate_model_choice(db, agent=agent, model_id=payload.model_id)
    if error:
        raise HTTPException(status_code=400, detail=error)

    agent.selected_model_id = payload.model_id
    await db.commit()
    await db.refresh(agent)
    return agent
