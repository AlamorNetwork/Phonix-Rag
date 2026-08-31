from typing import Any

from app.policies.risk import RiskLevel
from app.tools.base import Tool
from app.tools.sandbox import SandboxExecutor

MAX_READ_BYTES = 200_000
MAX_WRITE_BYTES = 200_000


class FilesystemReadTool(Tool):
    name = "filesystem.read"
    risk_level = RiskLevel.READ
    description = "Read a text file from the project workspace."

    async def execute(self, sandbox: SandboxExecutor, params: dict[str, Any]) -> dict[str, Any]:
        path = sandbox.resolve(params["path"])
        if not path.is_file():
            return {"error": f"file not found: {params['path']}"}
        content = path.read_text(encoding="utf-8", errors="replace")[:MAX_READ_BYTES]
        return {"path": params["path"], "content": content}


class FilesystemWriteTool(Tool):
    name = "filesystem.write"
    risk_level = RiskLevel.LOW
    description = "Create or overwrite a text file in the project workspace."

    async def execute(self, sandbox: SandboxExecutor, params: dict[str, Any]) -> dict[str, Any]:
        content = params.get("content", "")
        if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
            return {"error": "content exceeds max write size"}
        path = sandbox.resolve(params["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"path": params["path"], "bytes_written": len(content.encode("utf-8"))}
