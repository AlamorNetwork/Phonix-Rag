import asyncio
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.core.workspaces import workspace_path_for
from app.cost.engine import BudgetExceeded, CostEngine
from app.database.types import utcnow
from app.events.bus import EventBus
from app.models.agent import Agent
from app.models.agent_run import AgentRun
from app.models.model import Model
from app.models.project import Project
from app.providers.base import ModelProvider
from app.tools.gateway import ToolGateway, tool_definitions_for


class AgentRunner:
    """Drives the Manager agent's tool-calling loop end to end: model call -> (maybe) tool
    calls through the Tool Gateway -> feed results back -> repeat, with budget checks before
    every model call and every important step turned into an event. Runs as a background
    asyncio task so it can suspend for an unbounded amount of time waiting on a human approval
    without blocking the HTTP request that started it.
    """

    def __init__(
        self,
        session_maker: async_sessionmaker,
        provider: ModelProvider,
        tool_gateway: ToolGateway,
        event_bus: EventBus,
        cost_engine: CostEngine,
        settings: Settings,
    ):
        self.session_maker = session_maker
        self.provider = provider
        self.tool_gateway = tool_gateway
        self.event_bus = event_bus
        self.cost_engine = cost_engine
        self.settings = settings

    async def run(self, run_id: str) -> None:
        async with self.session_maker() as db:
            run = await db.get(AgentRun, run_id)
            agent = await db.get(Agent, run.agent_id)
            project = await db.get(Project, run.project_id)
            model = await self._resolve_model(db, agent)
            workspace_root = workspace_path_for(project.id, self.settings)
            workspace_root.mkdir(parents=True, exist_ok=True)

            run.status = "running"
            run.started_at = utcnow()
            await db.commit()
            await self.event_bus.publish(
                db, project_id=project.id, agent_run_id=run.id, event_type="agent.started",
                payload={"agent_role": agent.role},
            )

            try:
                await asyncio.wait_for(
                    self._loop(db, run=run, agent=agent, project_id=project.id, model=model, workspace_root=workspace_root),
                    timeout=agent.timeout_seconds,
                )
            except TimeoutError:
                run.status = "timeout"
                run.output_message = "Agent run exceeded its timeout."
            except BudgetExceeded as exc:
                run.status = "blocked"
                run.output_message = str(exc)
                await self.event_bus.publish(
                    db, project_id=project.id, agent_run_id=run.id, event_type="budget.exceeded",
                    payload={"detail": str(exc)},
                )
            except Exception as exc:  # noqa: BLE001 - a bug in one run must not crash the orchestrator
                run.status = "failed"
                run.output_message = f"Run failed: {exc}"

            run.finished_at = utcnow()
            await db.commit()
            await self.event_bus.publish(
                db, project_id=project.id, agent_run_id=run.id, event_type="agent.completed",
                payload={"status": run.status},
            )

    async def _resolve_model(self, db, agent: Agent) -> Model:
        model_id = agent.allowed_models[0] if agent.allowed_models else self.settings.liara_default_model
        result = await db.execute(select(Model).where(Model.model_id == model_id))
        model = result.scalars().first()
        if model is None:
            raise RuntimeError(f"model '{model_id}' is not registered in the Model Registry")
        return model

    async def _loop(self, db, *, run: AgentRun, agent: Agent, project_id: str, model: Model, workspace_root) -> None:
        messages: list[dict] = [
            {"role": "system", "content": agent.system_prompt},
            {"role": "user", "content": run.input_message},
        ]
        tools = tool_definitions_for(agent.allowed_tools)
        final_text = None

        for _ in range(agent.max_iterations):
            estimated_input_tokens = self.cost_engine.estimate_tokens(json.dumps(messages))
            estimated_output_tokens = 500
            estimated_cost = self.provider.estimate_cost(
                input_price_per_1k=model.input_price_per_1k,
                output_price_per_1k=model.output_price_per_1k,
                estimated_input_tokens=estimated_input_tokens,
                estimated_output_tokens=estimated_output_tokens,
            )
            await self.cost_engine.check_budget(
                db, agent_run_id=run.id, budget_usd=agent.budget_usd, estimated_cost=estimated_cost
            )

            await self.event_bus.publish(
                db, project_id=project_id, agent_run_id=run.id, event_type="model.request",
                payload={"model": model.model_id},
            )
            chat_result = await self.provider.chat(model=model.model_id, messages=messages, tools=tools)
            model_request = await self.cost_engine.record(
                db,
                agent_run_id=run.id,
                provider=self.provider,
                model_id=model.model_id,
                estimated_cost=estimated_cost,
                chat_result=chat_result,
                input_price_per_1k=model.input_price_per_1k,
                output_price_per_1k=model.output_price_per_1k,
            )
            await self.event_bus.publish(
                db, project_id=project_id, agent_run_id=run.id, event_type="model.response",
                payload={
                    "input_tokens": chat_result.usage.input_tokens,
                    "output_tokens": chat_result.usage.output_tokens,
                    "latency_ms": chat_result.latency_ms,
                },
            )
            await self.event_bus.publish(
                db, project_id=project_id, agent_run_id=run.id, event_type="cost.recorded",
                payload={"estimated_cost": estimated_cost, "actual_cost": model_request.actual_cost},
            )

            if chat_result.tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": chat_result.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                            }
                            for tc in chat_result.tool_calls
                        ],
                    }
                )
                for tool_call in chat_result.tool_calls:
                    result = await self.tool_gateway.dispatch(
                        db,
                        agent_run_id=run.id,
                        project_id=project_id,
                        workspace_root=workspace_root,
                        tool_name=tool_call.name,
                        params=tool_call.arguments,
                        requested_by=agent.role,
                    )
                    messages.append(
                        {"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(result)}
                    )
                continue

            final_text = chat_result.content
            break
        else:
            final_text = final_text or "Reached max iterations without a final answer."

        run.status = "completed"
        run.output_message = final_text
