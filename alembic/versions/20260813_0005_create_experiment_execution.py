"""Create experiment execution metadata tables.

Revision ID: 20260813_0005
Revises: 20260812_0004
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260813_0005"
down_revision: str | None = "20260812_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "experiment_specs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(128), nullable=False),
        sa.Column("research_job_id", sa.String(64), nullable=False),
        sa.Column("brief_version_id", sa.String(64), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("resource_version", sa.Integer(), nullable=False),
        sa.Column("spec_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("factor_ir_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_id", sa.String(128), nullable=False),
        sa.Column("snapshot_manifest_hash", sa.String(64), nullable=False),
        sa.Column("spec_payload", sa.JSON(), nullable=False),
        sa.Column("factor_ir_payload", sa.JSON(), nullable=False),
        sa.Column("snapshot_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(
            ["research_job_id"], ["research_jobs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["brief_version_id"], ["research_brief_versions.id"]),
    )
    for column in ("project_id", "research_job_id", "market"):
        op.create_index(f"ix_experiment_specs_{column}", "experiment_specs", [column])

    op.create_table(
        "experiment_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("experiment_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(128), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("run_fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("validation_summary", sa.JSON(), nullable=True),
        sa.Column("invariance", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["experiment_specs.id"], ondelete="CASCADE"
        ),
    )
    for column in ("experiment_id", "project_id", "market", "state"):
        op.create_index(f"ix_experiment_runs_{column}", "experiment_runs", [column])

    op.create_table(
        "experiment_attempts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["experiment_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_experiment_attempt_ordinal"),
    )
    op.create_index("ix_experiment_attempts_run_id", "experiment_attempts", ["run_id"])

    op.create_table(
        "experiment_artifacts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("content_hash", sa.String(80), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("attempt_id", sa.String(64), nullable=False),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(128), nullable=False),
        sa.Column("domain_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["experiment_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["attempt_id"], ["experiment_attempts.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_experiment_artifacts_run_id", "experiment_artifacts", ["run_id"]
    )
    op.create_index(
        "ix_experiment_artifacts_content_hash",
        "experiment_artifacts",
        ["content_hash"],
    )

    op.create_table(
        "experiment_lineage",
        sa.Column("edge_hash", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("source_artifact_hash", sa.String(80), nullable=False),
        sa.Column("target_artifact_hash", sa.String(80), nullable=False),
        sa.Column("relation", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["experiment_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_experiment_lineage_run_id", "experiment_lineage", ["run_id"])

    op.create_table(
        "experiment_command_receipts",
        sa.Column("actor_id", sa.String(255), primary_key=True),
        sa.Column("idempotency_key", sa.String(255), primary_key=True),
        sa.Column("request_hash", sa.String(80), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("experiment_command_receipts")
    op.drop_index("ix_experiment_lineage_run_id", table_name="experiment_lineage")
    op.drop_table("experiment_lineage")
    op.drop_index(
        "ix_experiment_artifacts_content_hash",
        table_name="experiment_artifacts",
    )
    op.drop_index("ix_experiment_artifacts_run_id", table_name="experiment_artifacts")
    op.drop_table("experiment_artifacts")
    op.drop_index("ix_experiment_attempts_run_id", table_name="experiment_attempts")
    op.drop_table("experiment_attempts")
    for column in ("state", "market", "project_id", "experiment_id"):
        op.drop_index(f"ix_experiment_runs_{column}", table_name="experiment_runs")
    op.drop_table("experiment_runs")
    for column in ("market", "research_job_id", "project_id"):
        op.drop_index(f"ix_experiment_specs_{column}", table_name="experiment_specs")
    op.drop_table("experiment_specs")
