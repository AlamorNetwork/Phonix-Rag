from typing import Any

from sqlalchemy import func, select

from app.models.agent import Agent
from app.models.model import Model
from app.models.model_request import ModelRequest
from app.policies.risk import RiskLevel
from app.tools.base import Tool, ToolContext

# A rough per-step budget the Manager can reason with when it has no better figure. Deliberately
# generous on output: agent steps that write files or reviews are output-heavy.
DEFAULT_INPUT_TOKENS = 8_000
DEFAULT_OUTPUT_TOKENS = 2_000
MAX_STEPS = 40


class CostEstimateTool(Tool):
    name = "cost.estimate"
    risk_level = RiskLevel.READ
    description = (
        "Project what a plan will cost before any of it runs. Give the steps you intend to "
        "carry out - each with the model it should run on and roughly how many input and "
        "output tokens it needs - and this returns the cost per step and the total, priced "
        "from the live model registry. Also reports what has already been spent on this run "
        "and how much budget is left."
    )

    async def execute(self, ctx: ToolContext, params: dict[str, Any]) -> dict[str, Any]:
        steps = params.get("steps") or []
        if not isinstance(steps, list):
            return {"error": "steps must be a list"}
        if len(steps) > MAX_STEPS:
            return {"error": f"too many steps: {len(steps)} (max {MAX_STEPS})"}

        async with ctx.session_maker() as db:
            agent = await db.get(Agent, ctx.agent_id)
            result = await db.execute(select(Model).where(Model.enabled.is_(True)))
            prices = {m.model_id: m for m in result.scalars().all()}

            spent = float(
                (
                    await db.execute(
                        select(
                            func.coalesce(
                                func.sum(func.coalesce(ModelRequest.actual_cost, ModelRequest.estimated_cost)), 0.0
                            )
                        ).where(ModelRequest.agent_run_id == ctx.agent_run_id)
                    )
                ).scalar_one()
            )

        default_model = agent.selected_model_id if agent else None
        breakdown = []
        total = 0.0
        unknown: list[str] = []

        for step in steps:
            if not isinstance(step, dict):
                continue
            model_id = step.get("model_id") or default_model
            model = prices.get(model_id)
            if model is None:
                unknown.append(str(model_id))
                continue

            in_tokens = _as_int(step.get("input_tokens"), DEFAULT_INPUT_TOKENS)
            out_tokens = _as_int(step.get("output_tokens"), DEFAULT_OUTPUT_TOKENS)
            runs = max(1, _as_int(step.get("runs"), 1))

            cost = runs * (
                (in_tokens / 1_000_000) * model.input_price_per_1m
                + (out_tokens / 1_000_000) * model.output_price_per_1m
            )
            total += cost
            breakdown.append(
                {
                    "step": step.get("name") or step.get("role") or "step",
                    "role": step.get("role"),
                    "model_id": model_id,
                    "runs": runs,
                    "input_tokens": in_tokens,
                    "output_tokens": out_tokens,
                    "estimated_cost_usd": round(cost, 6),
                }
            )

        result: dict[str, Any] = {
            "currency": "USD",
            "pricing_unit": "per 1M tokens",
            "steps": breakdown,
            "estimated_total_usd": round(total, 6),
            "already_spent_this_run_usd": round(spent, 6),
            "run_budget_usd": agent.budget_usd if agent else None,
        }
        if agent:
            remaining = agent.budget_usd - spent
            result["remaining_run_budget_usd"] = round(remaining, 6)
            result["fits_in_run_budget"] = total <= remaining
        if unknown:
            result["unknown_models"] = sorted(set(unknown))
        return result


def _as_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback
