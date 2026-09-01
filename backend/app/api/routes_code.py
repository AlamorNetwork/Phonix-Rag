from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import Settings, get_settings
from app.core.workspaces import workspace_path_for
from app.database.session import get_db
from app.models.project import Project
from app.models.user import User
from app.tools.sandbox import SandboxExecutor, SandboxViolation

router = APIRouter(prefix="/projects", tags=["code"])

# Directories that are noise rather than work product, and would bury the handful of files an
# agent actually wrote.
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", ".pytest_cache", ".next"}
MAX_ENTRIES = 800
MAX_FILE_BYTES = 400_000


class FileEntry(BaseModel):
    path: str
    name: str
    is_dir: bool
    size: int


class FileContent(BaseModel):
    path: str
    content: str
    size: int
    truncated: bool


class Commit(BaseModel):
    sha: str
    subject: str
    author: str
    when: str


async def _workspace(db: AsyncSession, project_id: str, settings: Settings) -> Path:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    root = workspace_path_for(project_id, settings)
    if not root.exists():
        raise HTTPException(status_code=404, detail="This project has no workspace yet")
    return root


def _safe(root: Path, relative: str) -> Path:
    """Every path from a client goes through the same guard the agents' tools use. These
    endpoints read straight off disk, so without it the API would be a way around the sandbox
    that the whole Tool Gateway exists to enforce."""
    try:
        return SandboxExecutor(root).resolve(relative)
    except SandboxViolation as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}/files", response_model=list[FileEntry])
async def list_files(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _current_user: User = Depends(get_current_user),
) -> list[FileEntry]:
    root = await _workspace(db, project_id, settings)

    entries: list[FileEntry] = []
    for path in sorted(root.rglob("*")):
        if len(entries) >= MAX_ENTRIES:
            break
        relative = path.relative_to(root)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        entries.append(
            FileEntry(
                path=str(relative).replace("\\", "/"),
                name=path.name,
                is_dir=path.is_dir(),
                size=path.stat().st_size if path.is_file() else 0,
            )
        )
    return entries


@router.get("/{project_id}/files/content", response_model=FileContent)
async def read_file(
    project_id: str,
    path: str = Query(..., description="workspace-relative path"),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _current_user: User = Depends(get_current_user),
) -> FileContent:
    root = await _workspace(db, project_id, settings)
    target = _safe(root, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="No such file")

    size = target.stat().st_size
    raw = target.read_bytes()[:MAX_FILE_BYTES]
    return FileContent(
        path=path,
        content=raw.decode("utf-8", errors="replace"),
        size=size,
        truncated=size > MAX_FILE_BYTES,
    )


@router.get("/{project_id}/git/log", response_model=list[Commit])
async def git_log(
    project_id: str,
    limit: int = Query(30, le=100),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _current_user: User = Depends(get_current_user),
) -> list[Commit]:
    root = await _workspace(db, project_id, settings)
    if not (root / ".git").exists():
        return []

    sep = "\x1f"
    result = await SandboxExecutor(root).run_command(
        ["git", "log", f"-{limit}", f"--pretty=format:%H{sep}%s{sep}%an{sep}%ad", "--date=iso"]
    )
    commits: list[Commit] = []
    for line in result["stdout"].splitlines():
        parts = line.split(sep)
        if len(parts) == 4:
            commits.append(Commit(sha=parts[0], subject=parts[1], author=parts[2], when=parts[3]))
    return commits


@router.get("/{project_id}/git/diff")
async def git_diff(
    project_id: str,
    sha: str | None = Query(None, description="commit to show; omitted means uncommitted changes"),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _current_user: User = Depends(get_current_user),
) -> dict:
    # Validated before any work is done: a client-supplied ref reaches git's argument list, so
    # only a plain hex sha is accepted - never something git could read as an option or a
    # revision expression.
    if sha is not None and not (7 <= len(sha) <= 40 and all(c in "0123456789abcdef" for c in sha.lower())):
        raise HTTPException(status_code=400, detail="sha must be a hex commit id")

    root = await _workspace(db, project_id, settings)
    if not (root / ".git").exists():
        return {"diff": "", "sha": sha}

    args = ["git", "show", "--patch", "--stat", sha] if sha else ["git", "diff", "HEAD"]
    result = await SandboxExecutor(root).run_command(args)
    return {"diff": result["stdout"][:200_000], "sha": sha}
