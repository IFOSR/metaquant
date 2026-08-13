"""Create append-only trial ledger table.

Revision ID: 20260814_0007
Revises: 20260814_0006
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0007"
down_revision: str | None = "20260814_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trial_ledgers",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("factor_ir_hash", sa.String(64), nullable=False),
        sa.Column("policy_id", sa.String(255), nullable=False),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("disposition", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["experiment_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_trial_ledgers_run_id", "trial_ledgers", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_trial_ledgers_run_id", table_name="trial_ledgers")
    op.drop_table("trial_ledgers")
