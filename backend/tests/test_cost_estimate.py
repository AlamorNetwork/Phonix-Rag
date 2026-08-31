from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.models.agent import Agent
from app.models.agent_run import AgentRun
from app.models.model import Model
from app.models.model_request import ModelRequest
from app.models.project import Project
from app.models.provider import Provider
from app.tools.base import ToolContext
from app.tools.cost_tools import CostEstimateTool
from app.tools.sandbox import SandboxExecutor


@pytest.fixture
async def ctx(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def _wal(conn, _rec):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    async with sm() as db:
        project = Project(name="p", idea="i", status="draft")
        provider = Provider(name="liara", base_url="http://x")
        db.add_all([project, provider])
        await db.commit()
        await db.refresh(project)
        await db.refresh(provider)

        # Real per-1M prices: Sonnet 4.6 is $3 in / $15 out, gpt-5-mini is $0.25 / $2.
        db.add_all([
            Model(provider_id=provider.id, model_id="anthropic/claude-sonnet-4.6",
                  input_price_per_1m=3.0, output_price_per_1m=15.0, context_window=1000000, enabled=True),
            Model(provider_id=provider.id, model_id="openai/gpt-5-mini",
                  input_price_per_1m=0.25, output_price_per_1m=2.0, context_window=400000, enabled=True),
        ])
        agent = Agent(project_id=project.id, role="manager", system_prompt="s",
                      allowed_tools=["cost.estimate"], allowed_models=[],
                      selected_model_id="anthropic/claude-sonnet-4.6",
                      budget_usd=2.0, max_iterations=5, timeout_seconds=30)
        db.add(agent)
        await db.commit()
        await db.refresh(agent)

        run = AgentRun(agent_id=agent.id, project_id=project.id, status="running", input_message="go")
        db.add(run)
        await db.commit()
        await db.refresh(run)

    yield ToolContext(sandbox=SandboxExecutor(tmp_path), session_maker=sm,
                      project_id=project.id, agent_run_id=run.id, agent_id=agent.id), sm, run
    await engine.dispose()


async def test_estimates_plan_cost_from_registry_prices(ctx):
    tool_ctx, _, _ = ctx
    result = await CostEstimateTool().execute(tool_ctx, {"steps": [
        # 100k in @ $3/1M = $0.30, 20k out @ $15/1M = $0.30  ->  $0.60
        {"name": "write code", "role": "coder", "model_id": "anthropic/claude-sonnet-4.6",
         "input_tokens": 100_000, "output_tokens": 20_000},
        # 2 runs x (50k in @ $0.25/1M = $0.0125 + 10k out @ $2/1M = $0.02) = $0.065
        {"name": "run tests", "role": "qa", "model_id": "openai/gpt-5-mini",
         "input_tokens": 50_000, "output_tokens": 10_000, "runs": 2},
    ]})

    assert result["steps"][0]["estimated_cost_usd"] == pytest.approx(0.60)
    assert result["steps"][1]["estimated_cost_usd"] == pytest.approx(0.065)
    assert result["estimated_total_usd"] == pytest.approx(0.665)
    assert result["pricing_unit"] == "per 1M tokens"


async def test_reports_remaining_budget_against_what_is_already_spent(ctx):
    tool_ctx, sm, run = ctx
    async with sm() as db:
        db.add(ModelRequest(agent_run_id=run.id, provider_name="liara",
                            model_id="anthropic/claude-sonnet-4.6", input_tokens=1000,
                            output_tokens=500, estimated_cost=0.4, actual_cost=0.5, latency_ms=10))
        await db.commit()

    result = await CostEstimateTool().execute(tool_ctx, {"steps": [
        {"name": "small step", "input_tokens": 10_000, "output_tokens": 1_000},
    ]})

    assert result["already_spent_this_run_usd"] == pytest.approx(0.5)
    assert result["run_budget_usd"] == pytest.approx(2.0)
    assert result["remaining_run_budget_usd"] == pytest.approx(1.5)
    assert result["fits_in_run_budget"] is True


async def test_flags_a_plan_that_would_blow_the_budget(ctx):
    tool_ctx, _, _ = ctx
    result = await CostEstimateTool().execute(tool_ctx, {"steps": [
        {"name": "huge", "model_id": "anthropic/claude-sonnet-4.6",
         "input_tokens": 1_000_000, "output_tokens": 200_000},
    ]})
    assert result["estimated_total_usd"] == pytest.approx(6.0)
    assert result["fits_in_run_budget"] is False


async def test_unknown_model_is_reported_not_silently_priced_at_zero(ctx):
    tool_ctx, _, _ = ctx
    result = await CostEstimateTool().execute(tool_ctx, {"steps": [
        {"name": "bad", "model_id": "nope/not-real", "input_tokens": 1000, "output_tokens": 1000},
    ]})
    assert result["unknown_models"] == ["nope/not-real"]
    assert result["estimated_total_usd"] == 0.0
