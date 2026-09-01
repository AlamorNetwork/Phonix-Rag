from typing import Any

from app.policies.risk import RiskLevel
from app.tools.base import Tool, ToolContext
from app.tools.sandbox_factory import is_isolated

# Running a command is not the same class of act as writing a file: it executes whatever the
# agent decided on, so it is the first tool that genuinely needs a container rather than a
# path restriction.
MAX_ARGS = 40
MAX_OUTPUT = 40_000


class TerminalExecTool(Tool):
    name = "terminal.exec"
    risk_level = RiskLevel.HIGH
    description = (
        "Run a command inside the project's sandbox - for example a test runner or a linter. "
        "The sandbox has no network access and cannot see anything outside this project's "
        "workspace. Give the command as a list of arguments, not a shell string."
    )

    async def execute(self, ctx: ToolContext, params: dict[str, Any]) -> dict[str, Any]:
        # Refuses rather than falling back: silently running an agent's command on the host
        # because isolation happened to be unavailable is exactly the failure this tool exists
        # to prevent.
        if not is_isolated(ctx.sandbox):
            return {
                "error": (
                    "refusing to run: this command needs a container sandbox and none is "
                    "available. Set SANDBOX_MODE=docker and make sure Docker is reachable."
                )
            }

        args = params.get("args")
        if isinstance(args, str):
            return {"error": "args must be a list of arguments, not a shell string"}
        if not isinstance(args, list) or not args:
            return {"error": "args must be a non-empty list"}
        if len(args) > MAX_ARGS:
            return {"error": f"too many arguments: {len(args)} (max {MAX_ARGS})"}
        if not all(isinstance(a, str) for a in args):
            return {"error": "every argument must be a string"}

        try:
            result = await ctx.sandbox.run_command(args, timeout=ctx.command_timeout)
        except TimeoutError:
            return {"error": f"command timed out after {ctx.command_timeout:.0f}s"}

        return {
            "command": args,
            "returncode": result["returncode"],
            "stdout": result["stdout"][:MAX_OUTPUT],
            "stderr": result["stderr"][:MAX_OUTPUT],
            "sandboxed": True,
        }


TERMINAL_TOOL_SCHEMAS: dict[str, dict] = {
    "terminal.exec": {
        "args": {
            "type": "array",
            "items": {"type": "string"},
            "description": 'command and arguments, e.g. ["python", "-m", "pytest", "-q"]',
        }
    }
}
