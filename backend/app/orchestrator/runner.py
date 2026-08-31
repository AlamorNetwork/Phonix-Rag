import asyncio
import json
import logging
from dataclasses import dataclass

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
from app.tools.gateway import ToolGateway, resolve_tool_name, tool_definitions_for


logger = logging.getLogger(__name__)


def _describe(exc: Exception) -> str:
    """Some exceptions carry no message at all - httpx.ReadTimeout being the one that bit us,
    leaving a run record that said only "Run failed: ". Always name the type."""
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


@dataclass
class _RunConfig:
    """Agent/model settings copied out of the DB up front, so the run loop never has to keep
    ORM objects (and therefore a session) alive across model calls and approval waits."""

    agent_id: str
    role: str
    system_prompt: str
    input_message: str
    project_name: str
    project_idea: str
    allowed_tools: list[str]
    budget_usd: float
    max_iterations: int


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
        # Every DB touch below opens its own short-lived session. A run can suspend for an
        # unbounded time waiting on a human approval, so holding one session (and its
        # connection) open for the whole run would pin a pool connection indefinitely and
        # leave a transaction idle-in-progress the entire time.
        async with self.session_maker() as db:
            run = await db.get(AgentRun, run_id)
            agent = await db.get(Agent, run.agent_id)
            project = await db.get(Project, run.project_id)
            project_id = run.project_id
            # Resolved here only to fail fast if the selected model isn't registered; the loop
            # re-resolves it every iteration so a mid-run switch is picked up.
            await self._resolve_model(db, agent)
            agent_role = agent.role
            agent_timeout = agent.timeout_seconds
            run_config = _RunConfig(
                agent_id=agent.id,
                role=agent.role,
                system_prompt=agent.system_prompt,
                input_message=run.input_message,
                project_name=project.name,
                project_idea=project.idea,
                allowed_tools=list(agent.allowed_tools),
                budget_usd=agent.budget_usd,
                max_iterations=agent.max_iterations,
            )

            run.status = "running"
            run.started_at = utcnow()
            await db.commit()

        workspace_root = workspace_path_for(project_id, self.settings)
        workspace_root.mkdir(parents=True, exist_ok=True)

        await self.event_bus.publish(
            self.session_maker, project_id=project_id, agent_run_id=run_id,
            event_type="agent.started", payload={"agent_role": agent_role},
        )

        status = "completed"
        output_message = None
        try:
            output_message = await asyncio.wait_for(
                self._loop(
                    run_id=run_id, project_id=project_id, config=run_config, workspace_root=workspace_root
                ),
                timeout=agent_timeout,
            )
        except TimeoutError:
            status = "timeout"
            output_message = "Agent run exceeded its timeout."
        except BudgetExceeded as exc:
            status = "blocked"
            output_message = str(exc)
            await self.event_bus.publish(
                self.session_maker, project_id=project_id, agent_run_id=run_id,
                event_type="budget.exceeded", payload={"detail": str(exc)},
            )
        except Exception as exc:  # noqa: BLE001 - a bug in one run must not crash the orchestrator
            logger.exception("agent run %s failed", run_id)
            status = "failed"
            output_message = f"Run failed: {_describe(exc)}"

        async with self.session_maker() as db:
            run = await db.get(AgentRun, run_id)
            run.status = status
            run.output_message = output_message
            run.finished_at = utcnow()
            await db.commit()

        await self.event_bus.publish(
            self.session_maker, project_id=project_id, agent_run_id=run_id,
            event_type="agent.completed", payload={"status": status},
        )

    async def _resolve_model(self, db, agent: Agent) -> Model:
        model_id = (
            agent.selected_model_id
            or (agent.allowed_models[0] if agent.allowed_models else None)
            or self.settings.liara_default_model
        )
        result = await db.execute(select(Model).where(Model.model_id == model_id))
        model = result.scalars().first()
        if model is None:
            raise RuntimeError(f"model '{model_id}' is not registered in the Model Registry")
        return model

    async def _loop(self, *, run_id: str, project_id: str, config: "_RunConfig", workspace_root) -> str:
        # The project's idea is the whole point of the run, so it goes in the context rather
        # than leaving the agent to guess from a bare instruction.
        messages: list[dict] = [
            {"role": "system", "content": config.system_prompt},
            {
                "role": "user",
                "content": (
                    f"Project: {config.project_name}\n\n"
                    f"Idea:\n{config.project_idea}\n\n"
                    f"Task:\n{config.input_message}"
                ),
            },
        ]
        tools = tool_definitions_for(config.allowed_tools)
        final_text = None

        for _ in range(config.max_iterations):
            # Re-read the model every iteration: a human (via the API) or the agent itself
            # (via model.switch) can change it mid-run, and the change must take effect on the
            # very next request rather than at the next run.
            async with self.session_maker() as db:
                agent = await db.get(Agent, config.agent_id)
                model = await self._resolve_model(db, agent)
                model_id = model.model_id
                input_price_per_1m = model.input_price_per_1m
                output_price_per_1m = model.output_price_per_1m

            estimated_input_tokens = self.cost_engine.estimate_tokens(json.dumps(messages))
            estimated_output_tokens = 500
            estimated_cost = self.provider.estimate_cost(
                input_price_per_1m=input_price_per_1m,
                output_price_per_1m=output_price_per_1m,
                estimated_input_tokens=estimated_input_tokens,
                estimated_output_tokens=estimated_output_tokens,
            )
            async with self.session_maker() as db:
                await self.cost_engine.check_budget(
                    db, agent_run_id=run_id, budget_usd=config.budget_usd, estimated_cost=estimated_cost
                )

            await self.event_bus.publish(
                self.session_maker, project_id=project_id, agent_run_id=run_id,
                event_type="model.request", payload={"model": model_id},
            )
            chat_result = await self.provider.chat(model=model_id, messages=messages, tools=tools)
            async with self.session_maker() as db:
                model_request = await self.cost_engine.record(
                    db,
                    agent_run_id=run_id,
                    provider=self.provider,
                    model_id=model_id,
                    estimated_cost=estimated_cost,
                    chat_result=chat_result,
                    input_price_per_1m=input_price_per_1m,
                    output_price_per_1m=output_price_per_1m,
                )
                actual_cost = model_request.actual_cost
            await self.event_bus.publish(
                self.session_maker, project_id=project_id, agent_run_id=run_id,
                event_type="model.response",
                payload={
                    "input_tokens": chat_result.usage.input_tokens,
                    "output_tokens": chat_result.usage.output_tokens,
                    "latency_ms": chat_result.latency_ms,
                },
            )
            await self.event_bus.publish(
                self.session_maker, project_id=project_id, agent_run_id=run_id,
                event_type="cost.recorded",
                payload={"estimated_cost": estimated_cost, "actual_cost": actual_cost},
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
                        self.session_maker,
                        agent_run_id=run_id,
                        project_id=project_id,
                        workspace_root=workspace_root,
                        # The model sees underscored names; translate back to the internal one.
                        tool_name=resolve_tool_name(tool_call.name),
                        params=tool_call.arguments,
                        requested_by=config.role,
                        agent_id=config.agent_id,
                    )
                    messages.append(
                        {"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(result)}
                    )
                continue

            final_text = chat_result.content
            break
        else:
            final_text = final_text or "Reached max iterations without a final answer."

        return final_text
