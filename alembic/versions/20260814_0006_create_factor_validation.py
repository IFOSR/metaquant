"""Create factor validation metadata table.

Revision ID: 20260814_0006
Revises: 20260813_0005
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0006"
down_revision: str | None = "20260813_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "factor_validations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("policy_id", sa.String(255), nullable=False),
        sa.Column("policy_hash", sa.String(64), nullable=False),
        sa.Column("label_id", sa.String(255), nullable=False),
        sa.Column("label_hash", sa.String(64), nullable=False),
        sa.Column("factor_artifact_hash", sa.String(80), nullable=False),
        sa.Column("output_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("report_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["experiment_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_factor_validations_run_id", "factor_validations", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_factor_validations_run_id", table_name="factor_validations")
    op.drop_table("factor_validations")
