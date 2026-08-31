"""add project_tasks

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-31

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ID = sa.String(36)


def upgrade() -> None:
    op.create_table(
        "project_tasks",
        sa.Column("id", ID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project_id", ID, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("assigned_role", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("agent_run_id", ID, nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_project_tasks_project_id", "project_tasks", ["project_id"])


def downgrade() -> None:
    op.drop_table("project_tasks")
