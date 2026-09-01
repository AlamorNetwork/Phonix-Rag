"""add security_findings

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ID = sa.String(36)


def upgrade() -> None:
    op.create_table(
        "security_findings",
        sa.Column("id", ID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project_id", ID, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("agent_run_id", ID, nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column("cve_id", sa.String(32), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("component", sa.String(255), nullable=True),
        sa.Column("file_path", sa.String(512), nullable=True),
        sa.Column("line", sa.Integer(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("remediation", sa.Text(), nullable=False),
        sa.Column("known_exploited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("epss_score", sa.Float(), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
    )
    for col in ("project_id", "source", "external_id", "cve_id", "severity", "status",
                "known_exploited", "fingerprint"):
        op.create_index(f"ix_security_findings_{col}", "security_findings", [col])


def downgrade() -> None:
    op.drop_table("security_findings")
