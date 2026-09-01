from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.approvals.service import ApprovalEngine, approval_engine
from app.core.config import get_settings
from app.database.types import new_uuid, utcnow
from app.events.bus import EventBus, event_bus
from app.models.tool_execution import ToolExecution
from app.policies.risk import PolicyEngine, policy_engine
from app.tools.base import Tool, ToolContext
from app.tools.cost_tools import CostEstimateTool
from app.tools.filesystem_tools import FilesystemReadTool, FilesystemWriteTool
from app.tools.git_tools import GitCommitTool, GitStatusTool
from app.tools.model_tools import ModelListTool, ModelSwitchTool
from app.tools.plan_tools import PLAN_TOOL_SCHEMAS, PlanReadTool, PlanSubmitTool
from app.tools.sandbox import SandboxExecutor, SandboxViolation
from app.tools.sandbox_factory import build_sandbox
from app.tools.terminal_tools import TERMINAL_TOOL_SCHEMAS, TerminalExecTool

TOOL_REGISTRY: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        FilesystemReadTool(),
        FilesystemWriteTool(),
        GitStatusTool(),
        GitCommitTool(),
        ModelListTool(),
        ModelSwitchTool(),
        CostEstimateTool(),
        PlanSubmitTool(),
        PlanReadTool(),
        TerminalExecTool(),
    )
}


# Tool names are dotted internally (filesystem.read) because that is how the spec names them
# and how they read in policy and audit records. Models cannot be sent those names: Anthropic
# constrains function names to ^[a-zA-Z0-9_-]{1,64}$, and a dotted name fails the whole request
# at the gateway. So dots become underscores on the wire and are translated back on the way in.
def to_wire_name(tool_name: str) -> str:
    return tool_name.replace(".", "_")


_WIRE_TO_INTERNAL: dict[str, str] = {to_wire_name(name): name for name in TOOL_REGISTRY}
assert len(_WIRE_TO_INTERNAL) == len(TOOL_REGISTRY), (
    "two tools collide once dots become underscores; rename one of them"
)


def resolve_tool_name(name: str) -> str:
    """Map a name the model used back to the internal tool name."""
    if name in TOOL_REGISTRY:
        return name
    return _WIRE_TO_INTERNAL.get(name, name)


class ToolGateway:
    """The only path from an agent to the filesystem/git. Every call goes through:
    Policy Engine (is approval needed?) -> Approval Engine (ask a human if so) ->
    Sandbox Executor (run it, scoped to the workspace) -> Result.
    """

    def __init__(self, policy_engine: PolicyEngine, approval_engine: ApprovalEngine, event_bus: EventBus):
        self.policy_engine = policy_engine
        self.approval_engine = approval_engine
        self.event_bus = event_bus

    async def dispatch(
        self,
        session_maker: async_sessionmaker,
        *,
        agent_run_id: str,
        project_id: str,
        workspace_root: Path,
        tool_name: str,
        params: dict[str, Any],
        requested_by: str = "agent",
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        tool = TOOL_REGISTRY.get(tool_name)
        if tool is None:
            return {"error": f"unknown tool: {tool_name}"}

        execution_id = new_uuid()
        async with session_maker() as db:
            db.add(
                ToolExecution(
                    id=execution_id,
                    agent_run_id=agent_run_id,
                    tool_name=tool_name,
                    risk_level=tool.risk_level.name,
                    input_params=params,
                    status="pending",
                )
            )
            await db.commit()

        await self.event_bus.publish(
            session_maker,
            project_id=project_id,
            agent_run_id=agent_run_id,
            event_type="tool.called",
            payload={"tool": tool_name, "risk": tool.risk_level.name, "execution_id": execution_id, "params": params},
        )

        if self.policy_engine.requires_approval(tool.risk_level):
            approval = await self.approval_engine.request_approval(
                session_maker,
                tool_execution_id=execution_id,
                risk_level=tool.risk_level.name,
                agent_run_id=agent_run_id,
                reason=f"{requested_by} wants to call {tool_name} (risk: {tool.risk_level.name})",
            )
            await self.event_bus.publish(
                session_maker,
                project_id=project_id,
                agent_run_id=agent_run_id,
                event_type="approval.required",
                payload={"approval_id": approval.id, "tool": tool_name, "risk": tool.risk_level.name, "reason": approval.reason},
            )

            # No DB session is held across this wait - it can last as long as a human takes.
            decision = await self.approval_engine.wait_for_decision(approval.id)

            await self.event_bus.publish(
                session_maker,
                project_id=project_id,
                agent_run_id=agent_run_id,
                event_type=f"approval.{decision}",
                payload={"approval_id": approval.id, "tool": tool_name},
            )

            if decision != "approved":
                async with session_maker() as db:
                    execution = await db.get(ToolExecution, execution_id)
                    execution.status = "denied"
                    await db.commit()
                return {"error": f"tool call '{tool_name}' was denied by human approver"}

        settings = get_settings()
        ctx = ToolContext(
            sandbox=build_sandbox(workspace_root, settings),
            command_timeout=settings.sandbox_timeout_seconds,
            session_maker=session_maker,
            project_id=project_id,
            agent_run_id=agent_run_id,
            agent_id=agent_id,
        )
        try:
            result = await tool.execute(ctx, params)
        except SandboxViolation as exc:
            result = {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - a tool failure must not crash the run
            result = {"error": f"tool execution failed: {exc}"}

        async with session_maker() as db:
            execution = await db.get(ToolExecution, execution_id)
            # Test the value, not the key: tools that report an error channel explicitly
            # (the git tools return "error": None on success) would otherwise be recorded as
            # failures, corrupting the audit trail and misleading any agent reading it.
            execution.status = "failed" if result.get("error") else "executed"
            execution.result = result
            execution.executed_at = utcnow()
            await db.commit()

        await self.event_bus.publish(
            session_maker,
            project_id=project_id,
            agent_run_id=agent_run_id,
            event_type="tool.completed",
            payload={"tool": tool_name, "execution_id": execution_id, "result": result},
        )
        return result


def tool_definitions_for(allowed_tools: list[str]) -> list[dict[str, Any]]:
    """OpenAI-compatible function-calling tool definitions for the given allow-list."""
    schemas = {
        "filesystem.read": {"path": {"type": "string", "description": "workspace-relative file path"}},
        "filesystem.write": {
            "path": {"type": "string", "description": "workspace-relative file path"},
            "content": {"type": "string", "description": "full file content to write"},
        },
        "git.status": {},
        "git.commit": {"message": {"type": "string", "description": "commit message"}},
        "model.list": {},
        "model.switch": {
            "model_id": {"type": "string", "description": "model id from model.list, e.g. qwen/qwen3.8-max"}
        },
        "cost.estimate": {
            "steps": {
                "type": "array",
                "description": "the steps you plan to carry out, in order",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "short name for the step"},
                        "role": {"type": "string", "description": "which agent role does it, e.g. coder"},
                        "model_id": {"type": "string", "description": "model for this step; defaults to the current one"},
                        "input_tokens": {"type": "integer", "description": "rough input tokens for one run"},
                        "output_tokens": {"type": "integer", "description": "rough output tokens for one run"},
                        "runs": {"type": "integer", "description": "how many times this step repeats"},
                    },
                    "required": ["name"],
                },
            }
        },
    }
    schemas.update(PLAN_TOOL_SCHEMAS)
    schemas.update(TERMINAL_TOOL_SCHEMAS)

    defs = []
    for name in allowed_tools:
        tool = TOOL_REGISTRY.get(name)
        if not tool:
            continue
        properties = schemas.get(name, {})
        defs.append(
            {
                "type": "function",
                "function": {
                    "name": to_wire_name(name),
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": list(properties.keys()),
                    },
                },
            }
        )
    return defs


tool_gateway = ToolGateway(policy_engine, approval_engine, event_bus)
