"""Create promotion records and combination pool factors.

Revision ID: 20260814_0009
Revises: 20260814_0008
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0009"
down_revision: str | None = "20260814_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "promotion_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("factor_ir_hash", sa.String(64), nullable=False),
        sa.Column("policy_id", sa.String(255), nullable=False),
        sa.Column("disposition", sa.String(32), nullable=False),
        sa.Column("total_score", sa.Float(), nullable=True),
        sa.Column("output_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("report_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["experiment_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_promotion_records_run_id", "promotion_records", ["run_id"])

    op.create_table(
        "combination_pool_factors",
        sa.Column("factor_ir_hash", sa.String(64), primary_key=True),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(32), nullable=False),
        sa.Column("promotion_evidence_hash", sa.String(64), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("combination_pool_factors")
    op.drop_index("ix_promotion_records_run_id", table_name="promotion_records")
    op.drop_table("promotion_records")
