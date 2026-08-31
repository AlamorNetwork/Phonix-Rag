from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import ID_LENGTH, IdMixin, TimestampMixin


class Approval(Base, IdMixin, TimestampMixin):
    __tablename__ = "approvals"

    tool_execution_id: Mapped[str] = mapped_column(String(ID_LENGTH), ForeignKey("tool_executions.id"), index=True)
    agent_run_id: Mapped[str] = mapped_column(String(ID_LENGTH), ForeignKey("agent_runs.id"), index=True)
    risk_level: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
