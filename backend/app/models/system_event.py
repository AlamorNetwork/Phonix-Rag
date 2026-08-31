from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import ID_LENGTH, IdMixin, TimestampMixin


class SystemEvent(Base, IdMixin, TimestampMixin):
    __tablename__ = "system_events"

    project_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), nullable=True, index=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
