from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.model import Model
from app.models.provider import Provider


async def seed_liara_provider(db: AsyncSession, settings: Settings) -> tuple[Provider, Model]:
    """Idempotently ensures a Liara provider + default model row exist in the registry
    (spec section 9: models are never hard-coded into agent/core logic)."""
    result = await db.execute(select(Provider).where(Provider.name == "liara"))
    provider = result.scalar_one_or_none()
    if provider is None:
        provider = Provider(name="liara", base_url=settings.liara_base_url)
        db.add(provider)
        await db.commit()
        await db.refresh(provider)

    result = await db.execute(
        select(Model).where(Model.provider_id == provider.id, Model.model_id == settings.liara_default_model)
    )
    model = result.scalar_one_or_none()
    if model is None:
        model = Model(
            provider_id=provider.id,
            model_id=settings.liara_default_model,
            input_price_per_1k=0.0,
            output_price_per_1k=0.0,
            context_window=128_000,
            enabled=True,
        )
        db.add(model)
        await db.commit()
        await db.refresh(model)

    return provider, model
