from pathlib import Path

from app.core.config import Settings
from app.tools.docker_sandbox import DockerSandboxExecutor
from app.tools.sandbox import SandboxExecutor


def build_sandbox(workspace_root: Path, settings: Settings) -> SandboxExecutor:
    """The executor a tool gets, per configuration.

    Returns the plain path-restricted executor in host mode, or when Docker is genuinely
    absent. Callers that need real isolation must ask `is_isolated()` rather than assuming.
    """
    if settings.sandbox_mode == "docker" and DockerSandboxExecutor.available():
        return DockerSandboxExecutor(
            workspace_root,
            image=settings.sandbox_image,
            memory=settings.sandbox_memory,
            cpus=settings.sandbox_cpus,
            pids_limit=settings.sandbox_pids_limit,
            network=settings.sandbox_network,
            user=settings.sandbox_user,
        )
    return SandboxExecutor(workspace_root)


def is_isolated(sandbox: SandboxExecutor) -> bool:
    """Whether this executor actually contains what it runs, as opposed to merely restricting
    which paths a cooperative tool touches."""
    return isinstance(sandbox, DockerSandboxExecutor) and sandbox.available()
