"""add security_controls and control_assessments

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ID = sa.String(36)


def upgrade() -> None:
    op.create_table(
        "security_controls",
        sa.Column("id", ID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("framework", sa.String(64), nullable=False),
        sa.Column("framework_version", sa.String(32), nullable=False),
        sa.Column("control_id", sa.String(64), nullable=False),
        sa.Column("chapter", sa.String(128), nullable=False),
        sa.Column("section", sa.String(128), nullable=False),
        sa.Column("requirement", sa.Text(), nullable=False),
        sa.Column("level", sa.String(16), nullable=True),
        sa.Column("verification", sa.JSON(), nullable=False),
        sa.Column("mappings", sa.JSON(), nullable=False),
    )
    op.create_index("ix_security_controls_framework", "security_controls", ["framework"])
    op.create_index("ix_security_controls_control_id", "security_controls", ["control_id"])
    op.create_index("ix_security_controls_level", "security_controls", ["level"])

    op.create_table(
        "control_assessments",
        sa.Column("id", ID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project_id", ID, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("control_id", ID, sa.ForeignKey("security_controls.id"), nullable=False),
        sa.Column("agent_run_id", ID, nullable=True),
        sa.Column("result", sa.String(24), nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("finding_id", ID, nullable=True),
    )
    op.create_index("ix_control_assessments_project_id", "control_assessments", ["project_id"])
    op.create_index("ix_control_assessments_control_id", "control_assessments", ["control_id"])
    op.create_index("ix_control_assessments_result", "control_assessments", ["result"])


def downgrade() -> None:
    op.drop_table("control_assessments")
    op.drop_table("security_controls")
