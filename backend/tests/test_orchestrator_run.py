import asyncio
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.approvals.service import ApprovalEngine, approval_engine
from app.core.config import Settings
from app.core.workspaces import workspace_path_for
from app.cost.engine import BudgetExceeded, cost_engine
from app.database.base import Base
from app.events.bus import event_bus
from app.models.agent import Agent
from app.models.agent_run import AgentRun
from app.models.approval import Approval
from app.models.model import Model
from app.models.model_request import ModelRequest
from app.models.project import Project
from app.models.provider import Provider
from app.orchestrator.runner import AgentRunner
from app.policies.risk import PolicyEngine
from app.providers.base import ChatResult, ModelProvider, ToolCall, Usage
from app.tools.gateway import ToolGateway


class ScriptedProvider(ModelProvider):
    """Fake provider that plays back a fixed sequence of ChatResults, so tests can drive the
    orchestrator loop deterministically without a live model or network."""

    name = "scripted"

    def __init__(self, script: list[ChatResult]):
        self._script = list(script)
        self.calls = 0

    async def chat(self, *, model, messages, tools=None) -> ChatResult:
        self.calls += 1
        return self._script.pop(0)

    def estimate_cost(self, *, input_price_per_1k, output_price_per_1k, estimated_input_tokens, estimated_output_tokens) -> float:
        return 0.0001


@pytest.fixture
async def db_session_maker(tmp_path: Path):
    # These tests run the orchestrator concurrently with a polling "human", so the DB must
    # support concurrent sessions the way production Postgres does:
    #   - a file-backed DB, not one shared :memory: connection, so each session really gets
    #     its own connection instead of interleaving on a single cursor
    #   - WAL, so the poller's reads don't block the runner's writes (in SQLite's default
    #     rollback-journal mode they do, and the runner stalls on the busy timeout)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_wal(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _make_project_agent_run(db_session_maker, *, budget_usd: float = 10.0, max_iterations: int = 5):
    async with db_session_maker() as db:
        project = Project(name="Test Project", idea="build a thing", status="draft")
        db.add(project)
        await db.commit()
        await db.refresh(project)

        provider_row = Provider(name="scripted", base_url="http://fake")
        db.add(provider_row)
        await db.commit()
        await db.refresh(provider_row)

        model_row = Model(
            provider_id=provider_row.id,
            model_id="fake-model",
            input_price_per_1k=0.0,
            output_price_per_1k=0.0,
            context_window=8192,
            enabled=True,
        )
        db.add(model_row)
        await db.commit()
        await db.refresh(model_row)

        agent = Agent(
            project_id=project.id,
            role="manager",
            system_prompt="test system prompt",
            allowed_tools=["filesystem.read", "filesystem.write"],
            allowed_models=["fake-model"],
            selected_model_id="fake-model",
            budget_usd=budget_usd,
            max_iterations=max_iterations,
            timeout_seconds=10,
        )
        db.add(agent)
        await db.commit()
        await db.refresh(agent)

        run = AgentRun(agent_id=agent.id, project_id=project.id, status="queued", input_message="build it")
        db.add(run)
        await db.commit()
        await db.refresh(run)

        return project, agent, run


def _runner(db_session_maker, provider: ModelProvider, workspaces_dir: Path, *, auto_approve_max_risk=None) -> AgentRunner:
    from app.policies.risk import RiskLevel

    policy = PolicyEngine(auto_approve_max_risk=auto_approve_max_risk if auto_approve_max_risk is not None else RiskLevel.READ)
    gateway = ToolGateway(policy, approval_engine, event_bus)
    settings = Settings(workspaces_dir=str(workspaces_dir))
    return AgentRunner(db_session_maker, provider, gateway, event_bus, cost_engine, settings)


async def test_run_completes_without_tool_calls(db_session_maker, tmp_path: Path):
    _, _, run = await _make_project_agent_run(db_session_maker)
    provider = ScriptedProvider([ChatResult(content="All good, nothing to do.", usage=Usage(10, 5))])
    runner = _runner(db_session_maker, provider, tmp_path)

    await runner.run(run.id)

    async with db_session_maker() as db:
        finished = await db.get(AgentRun, run.id)
        assert finished.status == "completed"
        assert finished.output_message == "All good, nothing to do."


async def test_run_auto_approves_read_risk_tool(db_session_maker, tmp_path: Path):
    _, _, run = await _make_project_agent_run(db_session_maker)
    workspace_root = workspace_path_for(run.project_id, Settings(workspaces_dir=str(tmp_path)))
    workspace_root.mkdir(parents=True, exist_ok=True)
    (workspace_root / "README.md").write_text("hi there")

    provider = ScriptedProvider(
        [
            ChatResult(
                content=None,
                tool_calls=[ToolCall(id="call_1", name="filesystem.read", arguments={"path": "README.md"})],
                usage=Usage(10, 5),
            ),
            ChatResult(content="Read the file, done.", usage=Usage(5, 5)),
        ]
    )
    runner = _runner(db_session_maker, provider, tmp_path)

    await runner.run(run.id)

    async with db_session_maker() as db:
        finished = await db.get(AgentRun, run.id)
        assert finished.status == "completed"
        result = await db.execute(select(Approval).where(Approval.agent_run_id == run.id))
        assert result.scalar_one_or_none() is None  # READ risk never needed a human


async def test_run_pauses_for_approval_and_resumes_on_decision(db_session_maker, tmp_path: Path):
    _, _, run = await _make_project_agent_run(db_session_maker)

    provider = ScriptedProvider(
        [
            ChatResult(
                content=None,
                tool_calls=[
                    ToolCall(id="call_1", name="filesystem.write", arguments={"path": "NOTES.md", "content": "hello"})
                ],
                usage=Usage(10, 5),
            ),
            ChatResult(content="Wrote the notes file.", usage=Usage(5, 5)),
        ]
    )
    runner = _runner(db_session_maker, provider, tmp_path)

    run_task = asyncio.create_task(runner.run(run.id))

    approval = None
    for _ in range(100):
        await asyncio.sleep(0.02)
        async with db_session_maker() as db:
            result = await db.execute(select(Approval).where(Approval.agent_run_id == run.id))
            approval = result.scalar_one_or_none()
        if approval is not None:
            break
    assert approval is not None, "approval was never created - tool call did not pause for a human"
    assert approval.status == "pending"

    async with db_session_maker() as db:
        approval = await db.get(Approval, approval.id)
        ApprovalEngine.mark_decided(approval, decision="approved", decided_by="test@example.com")
        await db.commit()
    resolved = approval_engine.resolve(approval.id, "approved")
    assert resolved is True

    await asyncio.wait_for(run_task, timeout=5)

    async with db_session_maker() as db:
        finished = await db.get(AgentRun, run.id)
        assert finished.status == "completed"
        assert finished.output_message == "Wrote the notes file."

    workspace_root = workspace_path_for(run.project_id, Settings(workspaces_dir=str(tmp_path)))
    assert (workspace_root / "NOTES.md").read_text() == "hello"


async def test_run_denied_approval_stops_tool_but_run_continues(db_session_maker, tmp_path: Path):
    _, _, run = await _make_project_agent_run(db_session_maker)

    provider = ScriptedProvider(
        [
            ChatResult(
                content=None,
                tool_calls=[
                    ToolCall(id="call_1", name="filesystem.write", arguments={"path": "NOTES.md", "content": "x"})
                ],
                usage=Usage(10, 5),
            ),
            ChatResult(content="Okay, I will not write the file.", usage=Usage(5, 5)),
        ]
    )
    runner = _runner(db_session_maker, provider, tmp_path)

    run_task = asyncio.create_task(runner.run(run.id))

    approval = None
    for _ in range(100):
        await asyncio.sleep(0.02)
        async with db_session_maker() as db:
            result = await db.execute(select(Approval).where(Approval.agent_run_id == run.id))
            approval = result.scalar_one_or_none()
        if approval is not None:
            break
    assert approval is not None

    async with db_session_maker() as db:
        approval = await db.get(Approval, approval.id)
        ApprovalEngine.mark_decided(approval, decision="denied", decided_by="test@example.com")
        await db.commit()
    approval_engine.resolve(approval.id, "denied")

    await asyncio.wait_for(run_task, timeout=5)

    async with db_session_maker() as db:
        finished = await db.get(AgentRun, run.id)
        assert finished.status == "completed"
        assert finished.output_message == "Okay, I will not write the file."

    workspace_root = workspace_path_for(run.project_id, Settings(workspaces_dir=str(tmp_path)))
    assert not (workspace_root / "NOTES.md").exists()


async def test_run_blocked_when_over_budget(db_session_maker, tmp_path: Path):
    _, _, run = await _make_project_agent_run(db_session_maker, budget_usd=0.0)
    provider = ScriptedProvider([ChatResult(content="should never get here", usage=Usage(10, 5))])
    runner = _runner(db_session_maker, provider, tmp_path)

    await runner.run(run.id)

    async with db_session_maker() as db:
        finished = await db.get(AgentRun, run.id)
        assert finished.status == "blocked"
    assert provider.calls == 0


async def test_agent_can_switch_model_mid_run(db_session_maker, tmp_path: Path):
    """model.switch must affect the very next model request, not just the next run."""
    _, agent, run = await _make_project_agent_run(db_session_maker)

    async with db_session_maker() as db:
        db_agent = await db.get(Agent, agent.id)
        db_agent.allowed_tools = ["model.switch"]
        db_agent.allowed_models = []  # any enabled model
        await db.commit()
        provider_row = (await db.execute(select(Provider))).scalars().first()
        db.add(
            Model(
                provider_id=provider_row.id,
                model_id="other-model",
                input_price_per_1k=0.0,
                output_price_per_1k=0.0,
                context_window=8192,
                enabled=True,
            )
        )
        await db.commit()

    provider = ScriptedProvider(
        [
            ChatResult(
                content=None,
                tool_calls=[ToolCall(id="c1", name="model.switch", arguments={"model_id": "other-model"})],
                usage=Usage(10, 5),
            ),
            ChatResult(content="Switched.", usage=Usage(5, 5)),
        ]
    )
    runner = _runner(db_session_maker, provider, tmp_path)
    run_task = asyncio.create_task(runner.run(run.id))

    approval = await _await_approval(db_session_maker, run.id)
    assert approval is not None, "model.switch should require human approval"
    assert approval.risk_level == "MEDIUM"
    await _decide(db_session_maker, approval.id, "approved")

    await asyncio.wait_for(run_task, timeout=5)

    async with db_session_maker() as db:
        assert (await db.get(Agent, agent.id)).selected_model_id == "other-model"
        requests = (await db.execute(select(ModelRequest).where(ModelRequest.agent_run_id == run.id))).scalars().all()
    # First request on the original model, second on the switched-to model.
    assert [r.model_id for r in requests] == ["fake-model", "other-model"]


async def _await_approval(db_session_maker, run_id: str):
    for _ in range(100):
        await asyncio.sleep(0.02)
        async with db_session_maker() as db:
            result = await db.execute(select(Approval).where(Approval.agent_run_id == run_id))
            approval = result.scalar_one_or_none()
        if approval is not None:
            return approval
    return None


async def _decide(db_session_maker, approval_id: str, decision: str) -> None:
    async with db_session_maker() as db:
        approval = await db.get(Approval, approval_id)
        ApprovalEngine.mark_decided(approval, decision=decision, decided_by="test@example.com")
        await db.commit()
    approval_engine.resolve(approval_id, decision)
