from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import ID_LENGTH, IdMixin, TimestampMixin


class Model(Base, IdMixin, TimestampMixin):
    __tablename__ = "models"

    provider_id: Mapped[str] = mapped_column(String(ID_LENGTH), ForeignKey("providers.id"), index=True)
    model_id: Mapped[str] = mapped_column(String(128))
    input_price_per_1k: Mapped[float] = mapped_column(Float, default=0.0)
    output_price_per_1k: Mapped[float] = mapped_column(Float, default=0.0)
    context_window: Mapped[int] = mapped_column(Integer, default=8192)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
