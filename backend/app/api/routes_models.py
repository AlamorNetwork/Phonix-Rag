from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.model import Model
from app.models.provider import Provider
from app.models.user import User
from app.schemas.model import ModelResponse, ProviderResponse

router = APIRouter(tags=["models"])


@router.get("/models", response_model=list[ModelResponse])
async def list_models(db: AsyncSession = Depends(get_db), _current_user: User = Depends(get_current_user)) -> list[Model]:
    result = await db.execute(select(Model))
    return list(result.scalars().all())


@router.get("/providers", response_model=list[ProviderResponse])
async def list_providers(db: AsyncSession = Depends(get_db), _current_user: User = Depends(get_current_user)) -> list[Provider]:
    result = await db.execute(select(Provider))
    return list(result.scalars().all())
