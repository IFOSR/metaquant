"""Create execution state table for paper/live kill switch and positions.

Revision ID: 20260814_0012
Revises: 20260814_0011
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0012"
down_revision: str | None = "20260814_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "execution_states",
        sa.Column("state_id", sa.String(64), primary_key=True),
        sa.Column("kill_switch_state", sa.String(16), nullable=False),
        sa.Column("tripped_by", sa.String(128), nullable=True),
        sa.Column("tripped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("shadow_positions", sa.JSON(), nullable=False),
        sa.Column("paper_positions", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("execution_states")
