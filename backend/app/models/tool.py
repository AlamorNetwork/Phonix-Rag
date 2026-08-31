from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import IdMixin, TimestampMixin


class Tool(Base, IdMixin, TimestampMixin):
    __tablename__ = "tools"

    name: Mapped[str] = mapped_column(String(64), unique=True)
    risk_level: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(Text, default="")
