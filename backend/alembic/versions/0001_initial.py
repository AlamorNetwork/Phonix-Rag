"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ID = sa.String(36)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", ID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "projects",
        sa.Column("id", ID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("idea", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
    )

    op.create_table(
        "workspaces",
        sa.Column("id", ID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project_id", ID, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("path", sa.String(512), nullable=False),
    )
    op.create_index("ix_workspaces_project_id", "workspaces", ["project_id"])

    op.create_table(
        "providers",
        sa.Column("id", ID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=False),
    )
    op.create_index("ix_providers_name", "providers", ["name"], unique=True)

    op.create_table(
        "models",
        sa.Column("id", ID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_id", ID, sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("input_price_per_1k", sa.Float(), nullable=False),
        sa.Column("output_price_per_1k", sa.Float(), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_models_provider_id", "models", ["provider_id"])

    op.create_table(
        "agents",
        sa.Column("id", ID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project_id", ID, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("allowed_tools", sa.JSON(), nullable=False),
        sa.Column("allowed_models", sa.JSON(), nullable=False),
        sa.Column("budget_usd", sa.Float(), nullable=False),
        sa.Column("max_iterations", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
    )
    op.create_index("ix_agents_project_id", "agents", ["project_id"])

    op.create_table(
        "agent_runs",
        sa.Column("id", ID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agent_id", ID, sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("project_id", ID, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("input_message", sa.Text(), nullable=False),
        sa.Column("output_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_runs_agent_id", "agent_runs", ["agent_id"])
    op.create_index("ix_agent_runs_project_id", "agent_runs", ["project_id"])

    op.create_table(
        "model_requests",
        sa.Column("id", ID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agent_run_id", ID, sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("provider_name", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Float(), nullable=False),
        sa.Column("actual_cost", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
    )
    op.create_index("ix_model_requests_agent_run_id", "model_requests", ["agent_run_id"])

    op.create_table(
        "tool_executions",
        sa.Column("id", ID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agent_run_id", ID, sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("input_params", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("approval_id", ID, nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tool_executions_agent_run_id", "tool_executions", ["agent_run_id"])

    op.create_table(
        "approvals",
        sa.Column("id", ID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tool_execution_id", ID, sa.ForeignKey("tool_executions.id"), nullable=False),
        sa.Column("agent_run_id", ID, sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("decided_by", sa.String(255), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_approvals_tool_execution_id", "approvals", ["tool_execution_id"])
    op.create_index("ix_approvals_agent_run_id", "approvals", ["agent_run_id"])

    op.create_table(
        "system_events",
        sa.Column("id", ID, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project_id", ID, nullable=True),
        sa.Column("agent_run_id", ID, nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_system_events_project_id", "system_events", ["project_id"])
    op.create_index("ix_system_events_agent_run_id", "system_events", ["agent_run_id"])
    op.create_index("ix_system_events_event_type", "system_events", ["event_type"])


def downgrade() -> None:
    op.drop_table("system_events")
    op.drop_table("approvals")
    op.drop_table("tool_executions")
    op.drop_table("model_requests")
    op.drop_table("agent_runs")
    op.drop_table("agents")
    op.drop_table("models")
    op.drop_table("providers")
    op.drop_table("workspaces")
    op.drop_table("projects")
    op.drop_table("users")
