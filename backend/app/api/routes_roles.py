from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.agents.roles import ROLE_ORDER, ROLES
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(tags=["roles"])


class RoleDefinition(BaseModel):
    name: str
    summary: str
    default_model: str
    budget_usd: float
    max_iterations: int
    timeout_seconds: int
    allowed_tools: list[str]


@router.get("/roles", response_model=list[RoleDefinition])
async def list_roles(_current_user: User = Depends(get_current_user)) -> list[RoleDefinition]:
    """The team's shape: what each role does, what it may call, and the model it starts on.
    Per-project overrides live on the agent rows; this is what a new project is seeded from."""
    return [
        RoleDefinition(
            name=r.name,
            summary=r.summary,
            default_model=r.default_model,
            budget_usd=r.budget_usd,
            max_iterations=r.max_iterations,
            timeout_seconds=r.timeout_seconds,
            allowed_tools=list(r.allowed_tools),
        )
        for r in (ROLES[name] for name in ROLE_ORDER)
    ]
