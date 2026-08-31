from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_request import ModelRequest
from app.providers.base import ChatResult, ModelProvider


class BudgetExceeded(Exception):
    def __init__(self, spent: float, estimated: float, budget: float):
        self.spent = spent
        self.estimated = estimated
        self.budget = budget
        super().__init__(
            f"budget exceeded: spent=${spent:.4f} + estimated=${estimated:.4f} > budget=${budget:.4f}"
        )


class CostEngine:
    """Core system component (not an agent, per spec section 27): estimates cost before every
    model call, guards it against the agent's budget, and records what was actually spent.
    """

    ROUGH_CHARS_PER_TOKEN = 4

    def estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // self.ROUGH_CHARS_PER_TOKEN)

    async def spent_so_far(self, db: AsyncSession, agent_run_id: str) -> float:
        result = await db.execute(
            select(func.coalesce(func.sum(func.coalesce(ModelRequest.actual_cost, ModelRequest.estimated_cost)), 0.0)).where(
                ModelRequest.agent_run_id == agent_run_id
            )
        )
        return float(result.scalar_one())

    async def check_budget(
        self,
        db: AsyncSession,
        *,
        agent_run_id: str,
        budget_usd: float,
        estimated_cost: float,
    ) -> None:
        spent = await self.spent_so_far(db, agent_run_id)
        if spent + estimated_cost > budget_usd:
            raise BudgetExceeded(spent, estimated_cost, budget_usd)

    async def record(
        self,
        db: AsyncSession,
        *,
        agent_run_id: str,
        provider: ModelProvider,
        model_id: str,
        estimated_cost: float,
        chat_result: ChatResult,
        input_price_per_1k: float,
        output_price_per_1k: float,
    ) -> ModelRequest:
        # Prefer what the provider actually billed; fall back to the price table only when the
        # provider reports no cost of its own.
        if chat_result.provider_cost is not None:
            actual_cost = chat_result.provider_cost
        else:
            actual_cost = provider.estimate_cost(
                input_price_per_1k=input_price_per_1k,
                output_price_per_1k=output_price_per_1k,
                estimated_input_tokens=chat_result.usage.input_tokens,
                estimated_output_tokens=chat_result.usage.output_tokens,
            )
        record = ModelRequest(
            agent_run_id=agent_run_id,
            provider_name=provider.name,
            model_id=model_id,
            input_tokens=chat_result.usage.input_tokens,
            output_tokens=chat_result.usage.output_tokens,
            cached_tokens=chat_result.usage.cached_tokens,
            estimated_cost=estimated_cost,
            actual_cost=actual_cost,
            latency_ms=chat_result.latency_ms,
            status="ok",
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record


cost_engine = CostEngine()
