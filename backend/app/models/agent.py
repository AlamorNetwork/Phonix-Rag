from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import ID_LENGTH, IdMixin, TimestampMixin


class Agent(Base, IdMixin, TimestampMixin):
    __tablename__ = "agents"

    project_id: Mapped[str] = mapped_column(String(ID_LENGTH), ForeignKey("projects.id"), index=True)
    role: Mapped[str] = mapped_column(String(64))
    system_prompt: Mapped[str] = mapped_column(Text)
    allowed_tools: Mapped[list] = mapped_column(JSON, default=list)
    # Governance allow-list. Empty means "any enabled model in the registry".
    allowed_models: Mapped[list] = mapped_column(JSON, default=list)
    # Currently active model, set either by a human via the API or by the agent itself via
    # the model.switch tool. Null falls back to the first allowed model, then to the default.
    selected_model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    budget_usd: Mapped[float] = mapped_column(Float, default=1.0)
    max_iterations: Mapped[int] = mapped_column(Integer, default=10)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=600)
