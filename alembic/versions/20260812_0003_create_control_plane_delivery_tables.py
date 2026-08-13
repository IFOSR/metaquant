"""Create transactional audit, outbox, inbox, and idempotency tables.

Revision ID: 20260812_0003
Revises: 20260811_0002
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260812_0003"
down_revision: str | None = "20260811_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=False),
        sa.Column("resource_version", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("parent_artifact_id", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("policy_decision", sa.String(length=128), nullable=True),
        sa.Column("before_hash", sa.String(length=80), nullable=True),
        sa.Column("after_hash", sa.String(length=80), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "action",
        "actor",
        "correlation_id",
        "occurred_at",
        "request_id",
        "resource_id",
    ):
        op.create_index(f"ix_audit_events_{column}", "audit_events", [column])

    op.create_table(
        "outbox_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("aggregate_type", sa.String(length=128), nullable=False),
        sa.Column("aggregate_id", sa.String(length=128), nullable=False),
        sa.Column("aggregate_version", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.Column(
            "published",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("event_id"),
    )
    for column in (
        "aggregate_id",
        "event_type",
        "occurred_at",
        "published",
    ):
        op.create_index(f"ix_outbox_events_{column}", "outbox_events", [column])

    op.create_table(
        "consumer_receipts",
        sa.Column("consumer_id", sa.String(length=128), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("consumer_id", "event_id"),
    )
    op.create_table(
        "idempotency_records",
        sa.Column("namespace", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("stored_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("namespace", "idempotency_key"),
    )


def downgrade() -> None:
    op.drop_table("idempotency_records")
    op.drop_table("consumer_receipts")
    for column in (
        "published",
        "occurred_at",
        "event_type",
        "aggregate_id",
    ):
        op.drop_index(f"ix_outbox_events_{column}", table_name="outbox_events")
    op.drop_table("outbox_events")
    for column in (
        "resource_id",
        "request_id",
        "occurred_at",
        "correlation_id",
        "actor",
        "action",
    ):
        op.drop_index(f"ix_audit_events_{column}", table_name="audit_events")
    op.drop_table("audit_events")
