from typing import Any

from app.policies.risk import RiskLevel
from app.tools.base import Tool, ToolContext
from app.tools.sandbox import SandboxExecutor


class GitStatusTool(Tool):
    name = "git.status"
    risk_level = RiskLevel.READ
    description = "Show the git status of the project workspace."

    async def execute(self, ctx: ToolContext, params: dict[str, Any]) -> dict[str, Any]:
        sandbox = ctx.sandbox
        await _ensure_repo(sandbox)
        result = await sandbox.run_command(["git", "status", "--porcelain=v1", "-b"])
        return {"output": result["stdout"], "error": result["stderr"] or None}


class GitCommitTool(Tool):
    name = "git.commit"
    risk_level = RiskLevel.MEDIUM
    description = "Stage all changes and create a git commit in the project workspace."

    async def execute(self, ctx: ToolContext, params: dict[str, Any]) -> dict[str, Any]:
        sandbox = ctx.sandbox
        await _ensure_repo(sandbox)
        message = params.get("message", "Phoenix Forge: automated commit")
        await sandbox.run_command(["git", "add", "-A"])
        result = await sandbox.run_command(["git", "commit", "-m", message, "--allow-empty"])
        sha = (await sandbox.run_command(["git", "rev-parse", "HEAD"]))["stdout"].strip()
        return {"commit_sha": sha, "output": result["stdout"], "error": result["stderr"] or None}


async def _ensure_repo(sandbox: SandboxExecutor) -> None:
    if not (sandbox.workspace_root / ".git").exists():
        await sandbox.run_command(["git", "init"])
        await sandbox.run_command(["git", "config", "user.email", "agent@phoenix-forge.local"])
        await sandbox.run_command(["git", "config", "user.name", "Phoenix Forge Agent"])
