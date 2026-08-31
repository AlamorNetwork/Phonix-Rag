from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import ID_LENGTH, IdMixin, TimestampMixin


class Workspace(Base, IdMixin, TimestampMixin):
    __tablename__ = "workspaces"

    project_id: Mapped[str] = mapped_column(String(ID_LENGTH), ForeignKey("projects.id"), index=True)
    path: Mapped[str] = mapped_column(String(512))
