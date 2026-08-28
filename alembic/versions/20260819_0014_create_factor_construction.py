"""Create factor construction tables (build specs, code bundles, build runs).

Revision ID: 20260819_0014
Revises: 20260819_0013
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260819_0014"
down_revision: str | None = "20260819_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "factor_build_specs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(128), nullable=False),
        sa.Column("research_job_id", sa.String(64), nullable=True),
        sa.Column("brief_version_id", sa.String(64), nullable=True),
        sa.Column("spec_hash", sa.String(80), nullable=False, unique=True),
        sa.Column("spec_payload", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("resource_version", sa.Integer(), nullable=False, default=1),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frozen_by", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(
            ["research_job_id"], ["research_jobs.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_factor_build_specs_project_id", "factor_build_specs", ["project_id"]
    )

    op.create_table(
        "factor_code_bundles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("spec_hash", sa.String(80), nullable=False),
        sa.Column("bundle_hash", sa.String(80), nullable=False, unique=True),
        sa.Column("manifest_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(["spec_hash"], ["factor_build_specs.spec_hash"]),
    )
    op.create_index(
        "ix_factor_code_bundles_spec_hash", "factor_code_bundles", ["spec_hash"]
    )

    op.create_table(
        "factor_build_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("spec_hash", sa.String(80), nullable=False),
        sa.Column("bundle_hash", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("run_fingerprint", sa.String(64), nullable=True, unique=True),
        sa.Column("weights_hash", sa.String(80), nullable=True),
        sa.Column("factor_values_hash", sa.String(80), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("logs_ref", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_factor_build_runs_spec_hash", "factor_build_runs", ["spec_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_factor_build_runs_spec_hash", table_name="factor_build_runs")
    op.drop_table("factor_build_runs")
    op.drop_index("ix_factor_code_bundles_spec_hash", table_name="factor_code_bundles")
    op.drop_table("factor_code_bundles")
    op.drop_index("ix_factor_build_specs_project_id", table_name="factor_build_specs")
    op.drop_table("factor_build_specs")
