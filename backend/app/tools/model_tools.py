from typing import Any

from sqlalchemy import select

from app.models.agent import Agent
from app.models.model import Model
from app.policies.risk import RiskLevel
from app.tools.base import Tool, ToolContext


class ModelListTool(Tool):
    name = "model.list"
    risk_level = RiskLevel.READ
    description = (
        "List the models this agent is allowed to run on, with their prices per 1k tokens "
        "and context windows, and which one is currently selected."
    )

    async def execute(self, ctx: ToolContext, params: dict[str, Any]) -> dict[str, Any]:
        async with ctx.session_maker() as db:
            agent = await db.get(Agent, ctx.agent_id)
            result = await db.execute(select(Model).where(Model.enabled.is_(True)))
            models = list(result.scalars().all())

        allowed = set(agent.allowed_models or [])
        return {
            "selected": agent.selected_model_id,
            "models": [
                {
                    "model_id": m.model_id,
                    "input_price_per_1m": m.input_price_per_1m,
                    "output_price_per_1m": m.output_price_per_1m,
                    "context_window": m.context_window,
                }
                for m in models
                if not allowed or m.model_id in allowed
            ],
        }


class ModelSwitchTool(Tool):
    name = "model.switch"
    # MEDIUM, not LOW: switching models changes what every subsequent request costs, so a
    # human approves it the same way they approve anything else that spends money differently.
    risk_level = RiskLevel.MEDIUM
    description = (
        "Switch which model this agent uses for its subsequent requests. Only models from "
        "model.list are accepted. Takes effect on the next model request."
    )

    async def execute(self, ctx: ToolContext, params: dict[str, Any]) -> dict[str, Any]:
        model_id = params.get("model_id")
        if not model_id:
            return {"error": "model_id is required"}

        async with ctx.session_maker() as db:
            agent = await db.get(Agent, ctx.agent_id)
            if agent is None:
                return {"error": "agent not found"}

            error = await validate_model_choice(db, agent=agent, model_id=model_id)
            if error:
                return {"error": error}

            previous = agent.selected_model_id
            agent.selected_model_id = model_id
            await db.commit()

        return {"previous_model": previous, "selected_model": model_id}


async def validate_model_choice(db, *, agent: Agent, model_id: str) -> str | None:
    """Shared guard for both the agent-facing tool and the human-facing API: the model must
    exist, be enabled, and be within the agent's allow-list. Returns an error string, or None
    when the choice is acceptable."""
    result = await db.execute(select(Model).where(Model.model_id == model_id))
    model = result.scalars().first()
    if model is None:
        return f"model '{model_id}' is not in the registry"
    if not model.enabled:
        return f"model '{model_id}' is disabled"
    if agent.allowed_models and model_id not in agent.allowed_models:
        return f"model '{model_id}' is not in this agent's allow-list"
    return None
