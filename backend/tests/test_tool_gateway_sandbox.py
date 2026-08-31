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


def test_dotted_tool_names_are_underscored_for_the_model():
    """Anthropic constrains function names to ^[a-zA-Z0-9_-]{1,64}$ - sending a dotted name
    fails the entire request at the gateway, which is what blocked every Opus-backed role."""
    from app.tools.gateway import resolve_tool_name, to_wire_name, tool_definitions_for

    defs = tool_definitions_for(["filesystem.read", "plan.submit"])
    names = [d["function"]["name"] for d in defs]

    assert names == ["filesystem_read", "plan_submit"]
    assert all("." not in n for n in names)


def test_wire_names_map_back_to_the_internal_tool():
    from app.tools.gateway import resolve_tool_name

    assert resolve_tool_name("filesystem_read") == "filesystem.read"
    assert resolve_tool_name("plan_submit") == "plan.submit"
    # A model that sends the internal name anyway still resolves.
    assert resolve_tool_name("filesystem.read") == "filesystem.read"
    # An unknown name passes through so the gateway reports it as unknown, not as something else.
    assert resolve_tool_name("nonsense") == "nonsense"
