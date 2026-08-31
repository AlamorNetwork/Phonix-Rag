import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.roles import ROLE_ORDER, ROLES, AgentRole
from app.core.config import Settings
from app.models.agent import Agent
from app.models.model import Model

logger = logging.getLogger(__name__)


async def _pick_model(db: AsyncSession, role: AgentRole, settings: Settings) -> str | None:
    """The role's preferred model if the registry has it, otherwise the configured default.

    A role's preference is a recommendation, not a requirement: the catalogue differs between
    accounts, and a project must still be usable when the ideal model is not on offer.
    """
    for candidate in (role.default_model, settings.liara_default_model):
        if not candidate:
            continue
        result = await db.execute(
            select(Model).where(Model.model_id == candidate, Model.enabled.is_(True))
        )
        if result.scalars().first() is not None:
            return candidate

    result = await db.execute(select(Model).where(Model.enabled.is_(True)))
    fallback = result.scalars().first()
    if fallback is None:
        logger.warning("no enabled models in the registry; agent for role %s has none", role.name)
        return None
    logger.info(
        "role %s: neither %s nor the default is available, falling back to %s",
        role.name, role.default_model, fallback.model_id,
    )
    return fallback.model_id


async def seed_project_agents(db: AsyncSession, project_id: str, settings: Settings) -> list[Agent]:
    """Give a project its full team. Idempotent: roles that already exist are left untouched,
    so this can also backfill a project created before a role was added."""
    result = await db.execute(select(Agent).where(Agent.project_id == project_id))
    existing = {a.role: a for a in result.scalars().all()}

    created = False
    for role_name in ROLE_ORDER:
        if role_name in existing:
            continue
        role = ROLES[role_name]
        agent = Agent(
            project_id=project_id,
            role=role.name,
            system_prompt=role.system_prompt,
            allowed_tools=list(role.allowed_tools),
            allowed_models=list(role.allowed_models),
            selected_model_id=await _pick_model(db, role, settings),
            budget_usd=role.budget_usd,
            max_iterations=role.max_iterations,
            timeout_seconds=role.timeout_seconds,
        )
        db.add(agent)
        existing[role_name] = agent
        created = True

    if created:
        await db.commit()
        for agent in existing.values():
            await db.refresh(agent)

    return [existing[name] for name in ROLE_ORDER if name in existing]


async def get_agent(db: AsyncSession, project_id: str, role: str) -> Agent | None:
    result = await db.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.role == role)
    )
    return result.scalar_one_or_none()
