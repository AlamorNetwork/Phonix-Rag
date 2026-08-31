from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import ID_LENGTH, IdMixin, TimestampMixin


class Model(Base, IdMixin, TimestampMixin):
    __tablename__ = "models"

    provider_id: Mapped[str] = mapped_column(String(ID_LENGTH), ForeignKey("providers.id"), index=True)
    model_id: Mapped[str] = mapped_column(String(128))
    # Per 1M tokens - the unit every provider quotes (Liara included), so the numbers here read
    # the same as the ones on the provider's own pricing page.
    input_price_per_1m: Mapped[float] = mapped_column(Float, default=0.0)
    output_price_per_1m: Mapped[float] = mapped_column(Float, default=0.0)
    context_window: Mapped[int] = mapped_column(Integer, default=8192)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
