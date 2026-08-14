"""Create alpha pool factors and independence reports.

Revision ID: 20260814_0008
Revises: 20260814_0007
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0008"
down_revision: str | None = "20260814_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alpha_pool_factors",
        sa.Column("factor_ir_hash", sa.String(64), primary_key=True),
        sa.Column("direction", sa.String(32), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("universe", sa.String(255), nullable=False),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("policy_id", sa.String(255), nullable=False),
        sa.Column("risk_premium", sa.Boolean(), nullable=False),
        sa.Column("lifecycle_state", sa.String(32), nullable=False),
        sa.Column("oos_ic", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "independence_reports",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("baseline_ic", sa.Float(), nullable=True),
        sa.Column("orthogonalized_ic", sa.Float(), nullable=True),
        sa.Column("max_abs_correlation", sa.Float(), nullable=True),
        sa.Column("replicated_risk_factor", sa.Boolean(), nullable=False),
        sa.Column("output_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("report_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["experiment_runs.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_independence_reports_run_id", "independence_reports", ["run_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_independence_reports_run_id", table_name="independence_reports")
    op.drop_table("independence_reports")
    op.drop_table("alpha_pool_factors")
