from pathlib import Path

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.approvals.service import approval_engine
from app.database.base import Base
from app.events.bus import event_bus
from app.models.tool_execution import ToolExecution
from app.policies.risk import PolicyEngine, RiskLevel
from app.tools.gateway import ToolGateway


@pytest.fixture
async def session_maker(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 's.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def _wal(conn, _rec):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _dispatch(session_maker, workspace: Path, tool: str, params: dict) -> str:
    gateway = ToolGateway(PolicyEngine(auto_approve_max_risk=RiskLevel.CRITICAL), approval_engine, event_bus)
    await gateway.dispatch(
        session_maker,
        agent_run_id="run1",
        project_id="proj1",
        workspace_root=workspace,
        tool_name=tool,
        params=params,
    )
    async with session_maker() as db:
        result = await db.execute(select(ToolExecution).where(ToolExecution.tool_name == tool))
        return result.scalars().first().status


async def test_successful_git_commit_is_recorded_as_executed(session_maker, tmp_path: Path):
    """git tools report their error channel explicitly as "error": None on success - the
    execution status must reflect the value, not the mere presence of the key."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.txt").write_text("hello")

    status = await _dispatch(session_maker, workspace, "git.commit", {"message": "first"})
    assert status == "executed"


async def test_genuinely_failing_tool_is_recorded_as_failed(session_maker, tmp_path: Path):
    workspace = tmp_path / "ws2"
    workspace.mkdir()
    status = await _dispatch(session_maker, workspace, "filesystem.read", {"path": "nope.txt"})
    assert status == "failed"
