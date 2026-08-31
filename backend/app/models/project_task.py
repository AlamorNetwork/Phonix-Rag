from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import ID_LENGTH, IdMixin, TimestampMixin


class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    IN_REVIEW = "in_review"
    REJECTED = "rejected"
    DONE = "done"
    BLOCKED = "blocked"

    TERMINAL = {DONE, BLOCKED}


class ProjectTask(Base, IdMixin, TimestampMixin):
    """One unit of the Manager's plan, owned by exactly one role.

    Tasks are created by the Manager as a proposal and stay inert until a human approves the
    plan - nothing here executes on its own.
    """

    __tablename__ = "project_tasks"

    project_id: Mapped[str] = mapped_column(String(ID_LENGTH), ForeignKey("projects.id"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    assigned_role: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.PENDING)
    # How many times the Coder has attempted this task; bounded so a Reviewer that keeps
    # rejecting cannot loop the pair forever.
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), nullable=True)
    # The Reviewer's findings when it sent the work back, fed into the Coder's next attempt.
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
