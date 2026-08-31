import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.model import Model
from app.models.provider import Provider
from app.providers.liara import LiaraProvider

logger = logging.getLogger(__name__)


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
            input_price_per_1m=0.0,
            output_price_per_1m=0.0,
            context_window=128_000,
            enabled=True,
        )
        db.add(model)
        await db.commit()
        await db.refresh(model)

    return provider, model


async def sync_models_from_provider(db: AsyncSession, settings: Settings) -> int:
    """Pull the provider's live model catalogue into the registry so a human (and the agent's
    model.switch tool) can pick from real models with real prices, instead of a hard-coded list.

    Best-effort by design: the gateway being unreachable must not stop the app from booting,
    so failures are logged and the previously synced rows stay in place.
    """
    if not settings.liara_api_key:
        logger.info("model sync skipped: no LIARA_API_KEY configured")
        return 0

    provider_row, _ = await seed_liara_provider(db, settings)
    provider = LiaraProvider(api_key=settings.liara_api_key, base_url=settings.liara_base_url)
    try:
        catalogue = await provider.list_models()
    except Exception:  # noqa: BLE001 - never let a provider outage block startup
        logger.exception("model sync failed; keeping existing registry entries")
        return 0

    result = await db.execute(select(Model).where(Model.provider_id == provider_row.id))
    existing = {m.model_id: m for m in result.scalars().all()}

    for entry in catalogue:
        row = existing.get(entry["model_id"])
        if row is None:
            db.add(
                Model(
                    provider_id=provider_row.id,
                    model_id=entry["model_id"],
                    input_price_per_1m=entry["input_price_per_1m"],
                    output_price_per_1m=entry["output_price_per_1m"],
                    context_window=entry["context_window"],
                    enabled=True,
                )
            )
        else:
            row.input_price_per_1m = entry["input_price_per_1m"]
            row.output_price_per_1m = entry["output_price_per_1m"]
            row.context_window = entry["context_window"]

    await db.commit()
    logger.info("model sync complete: %d models in catalogue", len(catalogue))
    return len(catalogue)
