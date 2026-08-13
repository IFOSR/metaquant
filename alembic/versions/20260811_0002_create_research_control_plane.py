"""Create research control-plane tables.

Revision ID: 20260811_0002
Revises: 20260811_0001
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260811_0002"
down_revision: str | None = "20260811_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_jobs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("resource_version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("market", sa.String(length=32), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("universe_ref", sa.Text(), nullable=False),
        sa.Column("frequency", sa.String(length=16), nullable=False),
        sa.Column("decision_clock", sa.String(length=128), nullable=False),
        sa.Column("trade_clock", sa.String(length=128), nullable=False),
        sa.Column("settlement_clock", sa.String(length=128), nullable=True),
        sa.Column("exchange_scope", sa.JSON(), nullable=False),
        sa.Column("contract_selection", sa.String(length=64), nullable=True),
        sa.Column("roll_policy", sa.Text(), nullable=True),
        sa.Column("horizon", sa.String(length=64), nullable=False),
        sa.Column("research_brief_version_id", sa.Text(), nullable=False),
        sa.Column("budget", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_jobs_market", "research_jobs", ["market"])
    op.create_index("ix_research_jobs_owner", "research_jobs", ["owner"])
    op.create_index("ix_research_jobs_state", "research_jobs", ["state"])

    op.create_table(
        "research_brief_versions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("resource_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("economic_mechanism", sa.Text(), nullable=False),
        sa.Column("expected_direction", sa.String(length=32), nullable=False),
        sa.Column("falsification_conditions", sa.JSON(), nullable=False),
        sa.Column("allowed_data_domains", sa.JSON(), nullable=False),
        sa.Column("forbidden_data_domains", sa.JSON(), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("evidence_ref_ids", sa.JSON(), nullable=False),
        sa.Column("uncertainties", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frozen_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["research_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "version", name="uq_brief_job_version"),
    )
    op.create_index(
        "ix_research_brief_versions_job_id",
        "research_brief_versions",
        ["job_id"],
    )

    op.create_table(
        "research_command_receipts",
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=80), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("actor_id", "idempotency_key"),
    )


def downgrade() -> None:
    op.drop_table("research_command_receipts")
    op.drop_index(
        "ix_research_brief_versions_job_id",
        table_name="research_brief_versions",
    )
    op.drop_table("research_brief_versions")
    op.drop_index("ix_research_jobs_state", table_name="research_jobs")
    op.drop_index("ix_research_jobs_owner", table_name="research_jobs")
    op.drop_index("ix_research_jobs_market", table_name="research_jobs")
    op.drop_table("research_jobs")
