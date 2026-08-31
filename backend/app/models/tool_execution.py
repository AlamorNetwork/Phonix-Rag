from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import ID_LENGTH, IdMixin, TimestampMixin


class ToolExecution(Base, IdMixin, TimestampMixin):
    __tablename__ = "tool_executions"

    agent_run_id: Mapped[str] = mapped_column(String(ID_LENGTH), ForeignKey("agent_runs.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(64))
    risk_level: Mapped[str] = mapped_column(String(16))
    input_params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # Not a DB-enforced FK: avoids a circular constraint with Approval (which points back at
    # this row's id). Approval is always created after the ToolExecution it belongs to.
    approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
