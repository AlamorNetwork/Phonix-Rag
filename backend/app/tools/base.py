from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.policies.risk import RiskLevel
from app.tools.sandbox import SandboxExecutor


@dataclass
class ToolContext:
    """Everything a tool is allowed to reach. Filesystem/git tools use `sandbox` (which is
    hard-scoped to one project's workspace); tools that act on Phoenix Forge's own state -
    model switching today, and the spec's system/network/database tools later - use
    `session_maker` and the ids below. A tool gets nothing beyond this.
    """

    sandbox: SandboxExecutor
    session_maker: async_sessionmaker
    project_id: str
    agent_run_id: str
    agent_id: str | None = None
    command_timeout: float = 120.0


class Tool(ABC):
    name: str
    risk_level: RiskLevel
    description: str = ""

    @abstractmethod
    async def execute(self, ctx: ToolContext, params: dict[str, Any]) -> dict[str, Any]:
        """Run the tool. Must only touch things reachable through `ctx`."""
