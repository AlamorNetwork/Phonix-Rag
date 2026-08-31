"""store model prices per 1M tokens instead of per 1k

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-31

Every provider (Liara included) quotes prices per 1M tokens, so storing per-1k meant the
registry never matched the numbers on the provider's pricing page. Existing rows are scaled
by 1000 rather than dropped, so a re-sync isn't required to keep the data correct.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("models", "input_price_per_1k", new_column_name="input_price_per_1m")
    op.alter_column("models", "output_price_per_1k", new_column_name="output_price_per_1m")
    op.execute(
        "UPDATE models SET input_price_per_1m = input_price_per_1m * 1000, "
        "output_price_per_1m = output_price_per_1m * 1000"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE models SET input_price_per_1m = input_price_per_1m / 1000, "
        "output_price_per_1m = output_price_per_1m / 1000"
    )
    op.alter_column("models", "input_price_per_1m", new_column_name="input_price_per_1k")
    op.alter_column("models", "output_price_per_1m", new_column_name="output_price_per_1k")
