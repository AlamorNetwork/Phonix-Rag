from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api import (
    routes_agents,
    routes_approvals,
    routes_auth,
    routes_health,
    routes_models,
    routes_plan,
    routes_projects,
    ws,
)
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.database.session import async_session_maker
from app.models.user import User
from app.models_registry.service import seed_liara_provider, sync_models_from_provider


async def _seed_initial_data() -> None:
    settings = get_settings()
    async with async_session_maker() as db:
        result = await db.execute(select(User).where(User.email == settings.admin_email))
        if result.scalar_one_or_none() is None:
            db.add(User(email=settings.admin_email, password_hash=hash_password(settings.admin_password)))
            await db.commit()
        await seed_liara_provider(db, settings)
        await sync_models_from_provider(db, settings)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    await _seed_initial_data()
    yield


app = FastAPI(title="Phoenix Forge API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # auth is a Bearer token, not cookies, so no credentialed CORS needed
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_health.router, prefix="/api")
app.include_router(routes_auth.router, prefix="/api")
app.include_router(routes_projects.router, prefix="/api")
app.include_router(routes_agents.router, prefix="/api")
app.include_router(routes_plan.router, prefix="/api")
app.include_router(routes_approvals.router, prefix="/api")
app.include_router(routes_models.router, prefix="/api")
app.include_router(ws.router)
