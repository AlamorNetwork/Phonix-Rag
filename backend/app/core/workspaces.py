from pathlib import Path

from app.core.config import Settings


def workspace_path_for(project_id: str, settings: Settings) -> Path:
    return Path(settings.workspaces_dir).resolve() / project_id
