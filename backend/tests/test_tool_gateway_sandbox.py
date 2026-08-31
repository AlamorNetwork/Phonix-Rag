from pathlib import Path

import pytest

from app.tools.base import ToolContext
from app.tools.filesystem_tools import FilesystemReadTool, FilesystemWriteTool
from app.tools.sandbox import SandboxExecutor, SandboxViolation, resolve_safe_path


def _ctx(tmp_path: Path) -> ToolContext:
    return ToolContext(
        sandbox=SandboxExecutor(tmp_path),
        session_maker=None,  # filesystem tools must never reach for the DB
        project_id="p1",
        agent_run_id="r1",
    )


def test_resolve_safe_path_allows_paths_inside_workspace(tmp_path: Path):
    resolved = resolve_safe_path(tmp_path, "notes/todo.md")
    assert tmp_path in resolved.parents


@pytest.mark.parametrize(
    "malicious_path",
    [
        "../secrets.txt",
        "../../etc/passwd",
        "a/../../b.txt",
    ],
)
def test_resolve_safe_path_rejects_traversal(tmp_path: Path, malicious_path: str):
    with pytest.raises(SandboxViolation):
        resolve_safe_path(tmp_path, malicious_path)


def test_resolve_safe_path_rejects_absolute_escape(tmp_path: Path):
    other_root = tmp_path.parent / "outside"
    with pytest.raises(SandboxViolation):
        resolve_safe_path(tmp_path, str(other_root / "file.txt"))


async def test_filesystem_write_then_read_round_trip(tmp_path: Path):
    ctx = _ctx(tmp_path)
    write_result = await FilesystemWriteTool().execute(ctx, {"path": "a/b.txt", "content": "hello"})
    assert write_result["bytes_written"] == 5

    read_result = await FilesystemReadTool().execute(ctx, {"path": "a/b.txt"})
    assert read_result["content"] == "hello"


async def test_filesystem_write_cannot_escape_workspace(tmp_path: Path):
    sandbox = SandboxExecutor(tmp_path)
    with pytest.raises(SandboxViolation):
        sandbox.resolve("../escape.txt")


async def test_filesystem_read_missing_file_returns_error_not_exception(tmp_path: Path):
    result = await FilesystemReadTool().execute(_ctx(tmp_path), {"path": "missing.txt"})
    assert "error" in result
