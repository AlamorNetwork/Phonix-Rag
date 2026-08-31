from pathlib import Path

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.roles import ROLE_ORDER, ROLES
from app.agents.service import get_agent, seed_project_agents
from app.core.config import Settings
from app.database.base import Base
from app.models.agent import Agent
from app.models.model import Model
from app.models.project import Project
from app.models.provider import Provider

SETTINGS = Settings(liara_default_model="fallback/default")


@pytest.fixture
async def db(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'r.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def _wal(conn, _rec):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        yield session
    await engine.dispose()


async def _project_with_models(db, model_ids: list[str]) -> str:
    project = Project(name="p", idea="i", status="draft")
    provider = Provider(name="liara", base_url="http://x")
    db.add_all([project, provider])
    await db.commit()
    await db.refresh(project)
    await db.refresh(provider)
    for mid in model_ids:
        db.add(Model(provider_id=provider.id, model_id=mid, input_price_per_1m=1.0,
                     output_price_per_1m=2.0, context_window=1000, enabled=True))
    await db.commit()
    return project.id


async def test_seeds_every_role_with_its_preferred_model(db):
    wanted = [ROLES[r].default_model for r in ROLE_ORDER]
    project_id = await _project_with_models(db, wanted)

    agents = await seed_project_agents(db, project_id, SETTINGS)

    assert [a.role for a in agents] == ROLE_ORDER
    for agent in agents:
        assert agent.selected_model_id == ROLES[agent.role].default_model
        assert agent.allowed_tools, f"{agent.role} has no tools"


async def test_reviewer_does_not_share_the_coders_model(db):
    """A model reviewing its own output shares its blind spots, so the two roles must not
    default to the same one."""
    assert ROLES["reviewer"].default_model != ROLES["coder"].default_model


async def test_coder_can_commit_but_manager_and_reviewer_cannot(db):
    assert "git.commit" in ROLES["coder"].allowed_tools
    assert "git.commit" not in ROLES["manager"].allowed_tools
    assert "git.commit" not in ROLES["reviewer"].allowed_tools
    # The Manager plans; it must not be able to write production code itself.
    assert "filesystem.write" not in ROLES["manager"].allowed_tools


async def test_falls_back_to_configured_default_when_preferred_model_is_absent(db):
    project_id = await _project_with_models(db, ["fallback/default"])

    agents = await seed_project_agents(db, project_id, SETTINGS)

    assert {a.selected_model_id for a in agents} == {"fallback/default"}


async def test_falls_back_to_any_enabled_model_when_nothing_preferred_exists(db):
    project_id = await _project_with_models(db, ["some/other-model"])

    agents = await seed_project_agents(db, project_id, SETTINGS)

    assert {a.selected_model_id for a in agents} == {"some/other-model"}


async def test_seeding_is_idempotent_and_preserves_a_chosen_model(db):
    project_id = await _project_with_models(db, [ROLES[r].default_model for r in ROLE_ORDER])
    await seed_project_agents(db, project_id, SETTINGS)

    coder = await get_agent(db, project_id, "coder")
    coder.selected_model_id = ROLES["manager"].default_model
    await db.commit()

    await seed_project_agents(db, project_id, SETTINGS)

    result = await db.execute(select(Agent).where(Agent.project_id == project_id))
    agents = list(result.scalars().all())
    assert len(agents) == len(ROLE_ORDER), "re-seeding duplicated agents"
    assert (await get_agent(db, project_id, "coder")).selected_model_id == ROLES["manager"].default_model
