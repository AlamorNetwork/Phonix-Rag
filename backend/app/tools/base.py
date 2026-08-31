from abc import ABC, abstractmethod
from typing import Any

from app.policies.risk import RiskLevel
from app.tools.sandbox import SandboxExecutor


class Tool(ABC):
    name: str
    risk_level: RiskLevel
    description: str = ""

    @abstractmethod
    async def execute(self, sandbox: SandboxExecutor, params: dict[str, Any]) -> dict[str, Any]:
        """Run the tool. Must only touch things reachable through `sandbox`."""
