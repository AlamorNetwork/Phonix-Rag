from pathlib import Path

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.models.project import Project, ProjectStatus
from app.models.project_task import ProjectTask, TaskStatus
from app.tools.base import ToolContext
from app.tools.plan_tools import PlanReadTool, PlanSubmitTool
from app.tools.sandbox import SandboxExecutor

GOOD_TASKS = [
    {"title": "Design the schema", "description": "tables and relations", "role": "architect",
     "estimated_cost_usd": 0.10},
    {"title": "Implement the API", "description": "endpoints per the design", "role": "coder",
     "estimated_cost_usd": 0.40},
    {"title": "Review the API", "description": "check against the design", "role": "reviewer",
     "estimated_cost_usd": 0.05},
]


@pytest.fixture
async def ctx(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'p.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def _wal(conn, _rec):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    async with sm() as db:
        project = Project(name="p", idea="i", status=ProjectStatus.DRAFT)
        db.add(project)
        await db.commit()
        await db.refresh(project)

    yield ToolContext(sandbox=SandboxExecutor(tmp_path), session_maker=sm,
                      project_id=project.id, agent_run_id="run1", agent_id=None), sm, project.id
    await engine.dispose()


async def test_submitting_a_plan_creates_ordered_tasks_awaiting_approval(ctx):
    tool_ctx, sm, project_id = ctx
    result = await PlanSubmitTool().execute(tool_ctx, {"tasks": GOOD_TASKS})

    assert result["submitted"] is True
    assert result["task_count"] == 3
    assert result["estimated_total_usd"] == pytest.approx(0.55)

    async with sm() as db:
        rows = (await db.execute(
            select(ProjectTask).where(ProjectTask.project_id == project_id).order_by(ProjectTask.order_index)
        )).scalars().all()
        assert [r.assigned_role for r in rows] == ["architect", "coder", "reviewer"]
        assert [r.order_index for r in rows] == [0, 1, 2]
        # Inert until a human approves: nothing is running.
        assert {r.status for r in rows} == {TaskStatus.PENDING}
        assert (await db.get(Project, project_id)).status == ProjectStatus.PLAN_PROPOSED


async def test_a_plan_with_no_reviewer_is_refused(ctx):
    tool_ctx, sm, project_id = ctx
    result = await PlanSubmitTool().execute(tool_ctx, {"tasks": [
        {"title": "Just build it", "description": "no review", "role": "coder"},
    ]})

    assert "reviewer" in result["error"]
    async with sm() as db:
        rows = (await db.execute(select(ProjectTask))).scalars().all()
        assert rows == [], "a refused plan must not leave tasks behind"
        assert (await db.get(Project, project_id)).status == ProjectStatus.DRAFT


async def test_unknown_role_is_refused_with_the_valid_options(ctx):
    tool_ctx, _, _ = ctx
    result = await PlanSubmitTool().execute(tool_ctx, {"tasks": [
        {"title": "Do security", "description": "x", "role": "security"},
        {"title": "Review", "description": "y", "role": "reviewer"},
    ]})
    assert "security" in result["error"]
    assert "architect" in result["error"]


async def test_resubmitting_replaces_the_previous_plan_rather_than_appending(ctx):
    tool_ctx, sm, project_id = ctx
    await PlanSubmitTool().execute(tool_ctx, {"tasks": GOOD_TASKS})
    await PlanSubmitTool().execute(tool_ctx, {"tasks": GOOD_TASKS[1:]})

    async with sm() as db:
        rows = (await db.execute(select(ProjectTask).where(ProjectTask.project_id == project_id))).scalars().all()
    assert len(rows) == 2, "resubmission should replace the plan, not stack a second copy"


async def test_cannot_replace_a_plan_that_is_already_approved_and_running(ctx):
    tool_ctx, sm, project_id = ctx
    await PlanSubmitTool().execute(tool_ctx, {"tasks": GOOD_TASKS})
    async with sm() as db:
        project = await db.get(Project, project_id)
        project.status = ProjectStatus.EXECUTING
        await db.commit()

    result = await PlanSubmitTool().execute(tool_ctx, {"tasks": GOOD_TASKS})

    assert "already approved" in result["error"]
    async with sm() as db:
        rows = (await db.execute(select(ProjectTask).where(ProjectTask.project_id == project_id))).scalars().all()
    assert len(rows) == 3, "the running plan must survive a rejected resubmission"


async def test_empty_plan_is_refused(ctx):
    tool_ctx, _, _ = ctx
    assert "error" in await PlanSubmitTool().execute(tool_ctx, {"tasks": []})


async def test_plan_read_returns_what_was_submitted(ctx):
    tool_ctx, _, _ = ctx
    await PlanSubmitTool().execute(tool_ctx, {"tasks": GOOD_TASKS})

    result = await PlanReadTool().execute(tool_ctx, {})

    assert result["project_status"] == ProjectStatus.PLAN_PROPOSED
    assert [t["role"] for t in result["tasks"]] == ["architect", "coder", "reviewer"]
