from pathlib import Path, PurePosixPath

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
            host_workspace_root=to_host_path(workspace_root, settings),
        )
    return SandboxExecutor(workspace_root)


def is_isolated(sandbox: SandboxExecutor) -> bool:
    """Whether this executor actually contains what it runs, as opposed to merely restricting
    which paths a cooperative tool touches."""
    return isinstance(sandbox, DockerSandboxExecutor) and sandbox.available()


def to_host_path(workspace_root: Path, settings: Settings) -> PurePosixPath:
    """Rewrite a path this process can see into the equivalent path on the host.

    Identity when workspaces_host_dir is unset, which is the case whenever this process is not
    itself containerised.
    """
    resolved = workspace_root.resolve()
    if not settings.workspaces_host_dir:
        return PurePosixPath(resolved)
    local_root = Path(settings.workspaces_dir).resolve()
    try:
        relative = resolved.relative_to(local_root)
    except ValueError:
        return PurePosixPath(resolved)
    return PurePosixPath(settings.workspaces_host_dir) / relative
