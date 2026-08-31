from pathlib import Path

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.roles import ROLE_ORDER
from app.agents.service import seed_project_agents
from app.approvals.service import approval_engine
from app.core.config import Settings
from app.cost.engine import cost_engine
from app.database.base import Base
from app.events.bus import event_bus
from app.models.model import Model
from app.models.project import Project, ProjectStatus
from app.models.project_task import ProjectTask, TaskStatus
from app.models.provider import Provider
from app.orchestrator.project_runner import MAX_ATTEMPTS, ProjectRunner
from app.policies.risk import PolicyEngine, RiskLevel
from app.providers.base import ChatResult, ModelProvider, Usage
from app.tools.gateway import ToolGateway

MODEL_ID = "fake/model"


class RoleScriptedProvider(ModelProvider):
    """Answers according to which role is talking, so a test can script the whole team rather
    than a single agent. Records the order roles were called in."""

    name = "role-scripted"

    def __init__(self, replies: dict[str, list[str]]):
        self._replies = {k: list(v) for k, v in replies.items()}
        self.calls: list[str] = []
        self.prompts: list[str] = []

    async def chat(self, *, model, messages, tools=None) -> ChatResult:
        system = messages[0]["content"]
        role = next((r for r in ROLE_ORDER if f"You are the {r.capitalize()}" in system), "unknown")
        self.calls.append(role)
        self.prompts.append(messages[1]["content"])
        queue = self._replies.get(role)
        reply = queue.pop(0) if queue else "done"
        return ChatResult(content=reply, usage=Usage(5, 5))

    def estimate_cost(self, **kwargs) -> float:
        return 0.0


@pytest.fixture
async def env(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'pr.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def _wal(conn, _rec):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(workspaces_dir=str(tmp_path), liara_default_model=MODEL_ID)

    async with sm() as db:
        project = Project(name="p", idea="build a thing", status=ProjectStatus.EXECUTING)
        provider = Provider(name="liara", base_url="http://x")
        db.add_all([project, provider])
        await db.commit()
        await db.refresh(project)
        await db.refresh(provider)
        db.add(Model(provider_id=provider.id, model_id=MODEL_ID, input_price_per_1m=0.0,
                     output_price_per_1m=0.0, context_window=8192, enabled=True))
        await db.commit()
        await seed_project_agents(db, project.id, settings)

    yield sm, settings, project.id
    await engine.dispose()


async def _add_tasks(sm, project_id: str, specs: list[tuple[str, str]]) -> None:
    async with sm() as db:
        for i, (role, title) in enumerate(specs):
            db.add(ProjectTask(project_id=project_id, order_index=i, title=title,
                               description="do it", assigned_role=role, status=TaskStatus.PENDING))
        await db.commit()


def _runner(sm, settings, provider) -> ProjectRunner:
    gateway = ToolGateway(PolicyEngine(auto_approve_max_risk=RiskLevel.CRITICAL), approval_engine, event_bus)
    return ProjectRunner(sm, provider, gateway, event_bus, cost_engine, settings)


async def _statuses(sm, project_id: str) -> list[tuple[str, str]]:
    async with sm() as db:
        rows = (await db.execute(
            select(ProjectTask).where(ProjectTask.project_id == project_id).order_by(ProjectTask.order_index)
        )).scalars().all()
        return [(t.assigned_role, t.status) for t in rows]


async def test_runs_tasks_in_order_and_completes_the_project(env):
    sm, settings, project_id = env
    await _add_tasks(sm, project_id, [("architect", "design"), ("coder", "build"), ("reviewer", "check")])
    provider = RoleScriptedProvider({"reviewer": ["Looks correct. I read main.py and checked each case."]})

    await _runner(sm, settings, provider).run(project_id)

    assert provider.calls == ["architect", "coder", "reviewer"]
    assert await _statuses(sm, project_id) == [
        ("architect", TaskStatus.DONE),
        ("coder", TaskStatus.DONE),
        ("reviewer", TaskStatus.DONE),
    ]
    async with sm() as db:
        assert (await db.get(Project, project_id)).status == ProjectStatus.COMPLETED


async def test_a_rejection_sends_the_coder_task_back_and_reruns_it(env):
    sm, settings, project_id = env
    await _add_tasks(sm, project_id, [("coder", "build"), ("reviewer", "check")])
    provider = RoleScriptedProvider({
        "reviewer": ["REJECTED - main.py line 4 divides by zero when n is 0.", "Fixed now, verified."],
    })

    await _runner(sm, settings, provider).run(project_id)

    assert provider.calls == ["coder", "reviewer", "coder", "reviewer"]
    assert await _statuses(sm, project_id) == [("coder", TaskStatus.DONE), ("reviewer", TaskStatus.DONE)]


async def test_the_coder_is_told_what_the_reviewer_found(env):
    sm, settings, project_id = env
    await _add_tasks(sm, project_id, [("coder", "build"), ("reviewer", "check")])
    provider = RoleScriptedProvider({
        "reviewer": ["REJECTED - main.py line 4 divides by zero when n is 0.", "Good now."],
    })

    await _runner(sm, settings, provider).run(project_id)

    retry_prompt = provider.prompts[2]
    assert "divides by zero" in retry_prompt, "the coder must receive the reviewer's findings"


async def test_repeated_rejection_blocks_instead_of_looping_forever(env):
    sm, settings, project_id = env
    await _add_tasks(sm, project_id, [("coder", "build"), ("reviewer", "check")])
    provider = RoleScriptedProvider({"reviewer": ["REJECTED - still broken."] * 10})

    await _runner(sm, settings, provider).run(project_id)

    coder_calls = provider.calls.count("coder")
    assert coder_calls <= MAX_ATTEMPTS, f"coder ran {coder_calls} times; loop protection failed"
    statuses = dict(await _statuses(sm, project_id))
    assert statuses["coder"] == TaskStatus.BLOCKED
    async with sm() as db:
        assert (await db.get(Project, project_id)).status != ProjectStatus.COMPLETED


async def test_a_failed_agent_run_blocks_rather_than_marking_the_task_done(env):
    sm, settings, project_id = env
    await _add_tasks(sm, project_id, [("coder", "build"), ("reviewer", "check")])

    class Exploding(RoleScriptedProvider):
        async def chat(self, *, model, messages, tools=None):
            raise RuntimeError("provider is down")

    await _runner(sm, settings, Exploding({})).run(project_id)

    statuses = dict(await _statuses(sm, project_id))
    assert statuses["coder"] == TaskStatus.BLOCKED
    assert statuses["reviewer"] == TaskStatus.PENDING, "the plan must not run on past a blocked task"


async def test_prose_mentioning_problems_is_not_treated_as_a_rejection(env):
    """The verdict is a deliberate marker, not something inferred from a review that happens to
    discuss problems it considered and dismissed."""
    sm, settings, project_id = env
    await _add_tasks(sm, project_id, [("coder", "build"), ("reviewer", "check")])
    provider = RoleScriptedProvider({
        "reviewer": ["I considered whether this was broken or wrong, and it is not. Approved."],
    })

    await _runner(sm, settings, provider).run(project_id)

    assert provider.calls == ["coder", "reviewer"]
    assert await _statuses(sm, project_id) == [("coder", TaskStatus.DONE), ("reviewer", TaskStatus.DONE)]
