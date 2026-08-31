import asyncio
from pathlib import Path


class SandboxViolation(Exception):
    """Raised when a tool tries to touch anything outside its workspace."""


def resolve_safe_path(workspace_root: Path, relative_path: str) -> Path:
    """Resolve `relative_path` inside `workspace_root`, rejecting any attempt to escape it
    (via `..`, absolute paths, or symlinks that point outside). This is the only thing
    standing between an agent-requested path and the real filesystem, so it fails closed.
    """
    workspace_root = workspace_root.resolve()
    candidate = (workspace_root / relative_path).resolve()
    if candidate != workspace_root and workspace_root not in candidate.parents:
        raise SandboxViolation(
            f"Path '{relative_path}' resolves outside the workspace sandbox"
        )
    return candidate


class SandboxExecutor:
    """Executes tool actions scoped to a single project's workspace directory.

    This is a path-restricted local executor, not a container. It exists behind the same
    interface a future `DockerSandboxExecutor` would implement, so Phase 1+ can swap in real
    per-workspace container isolation (CPU/RAM/disk/network limits, as per the full spec)
    without touching the Tool Gateway or any tool implementation.
    """

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative_path: str) -> Path:
        return resolve_safe_path(self.workspace_root, relative_path)

    async def run_command(self, args: list[str], timeout: float = 30.0) -> dict:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(self.workspace_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            raise
        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
        }
