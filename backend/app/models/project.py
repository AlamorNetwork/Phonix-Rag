from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import IdMixin, TimestampMixin


class ProjectStatus:
    """A project moves forward only through a human: it cannot leave PLAN_PROPOSED on its own."""

    DRAFT = "draft"
    PLANNING = "planning"
    PLAN_PROPOSED = "plan_proposed"
    EXECUTING = "executing"
    COMPLETED = "completed"


class Project(Base, IdMixin, TimestampMixin):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255))
    idea: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default=ProjectStatus.DRAFT)
