from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.routes_code import _safe, git_diff


def test_safe_allows_paths_inside_the_workspace(tmp_path: Path):
    (tmp_path / "main.py").write_text("x = 1")
    assert _safe(tmp_path, "main.py").is_file()


@pytest.mark.parametrize(
    "attack",
    [
        "../../etc/passwd",
        "../secrets.env",
        "a/../../outside.txt",
        "/etc/shadow",
    ],
)
def test_safe_rejects_paths_that_escape_the_workspace(tmp_path: Path, attack: str):
    """These endpoints read straight off disk. Without this guard the API would be a way
    around the sandbox that the Tool Gateway exists to enforce."""
    with pytest.raises(HTTPException) as excinfo:
        _safe(tmp_path, attack)
    assert excinfo.value.status_code == 400


@pytest.mark.parametrize(
    "bad_sha",
    [
        "--output=/tmp/pwned",
        "HEAD; rm -rf /",
        "$(whoami)",
        "main..HEAD",
        "-n1",
    ],
)
async def test_git_diff_refuses_anything_that_is_not_a_plain_commit_id(bad_sha: str):
    """A client-supplied ref lands in git's argument list, so only a hex sha is accepted -
    never something git could read as an option or a revision expression."""
    with pytest.raises(HTTPException) as excinfo:
        await git_diff(project_id="p", sha=bad_sha, db=None, settings=None, _current_user=None)
    assert excinfo.value.status_code == 400
