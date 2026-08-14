"""Create market data source, PIT observation, and universe history tables.

Revision ID: 20260814_0011
Revises: 20260814_0010
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0011"
down_revision: str | None = "20260814_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_data_sources",
        sa.Column("source_id", sa.String(128), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("license", sa.String(255), nullable=False),
        sa.Column("coverage_scope", sa.String(255), nullable=False),
        sa.Column("revision_capable", sa.Boolean(), nullable=False),
        sa.Column("pit_capable", sa.Boolean(), nullable=False),
        sa.Column("cross_validation_status", sa.String(32), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "pit_observations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("dataset_id", sa.String(128), nullable=False),
        sa.Column("field", sa.String(255), nullable=False),
        sa.Column("instrument_id", sa.String(64), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision_id", sa.String(64), nullable=False),
        sa.Column("license_tag", sa.String(128), nullable=False),
        sa.Column("value_type", sa.String(32), nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
    )
    op.create_index(
        "ix_pit_observations_field_time",
        "pit_observations",
        ["field", "event_time"],
    )
    op.create_index(
        "ix_pit_observations_instrument_field",
        "pit_observations",
        ["instrument_id", "field"],
    )

    op.create_table(
        "universe_history",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("universe_ref", sa.String(255), nullable=False),
        sa.Column("instrument_id", sa.String(64), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("membership_status", sa.String(32), nullable=False),
    )
    op.create_index(
        "ix_universe_history_ref_instrument",
        "universe_history",
        ["universe_ref", "instrument_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_universe_history_ref_instrument", table_name="universe_history")
    op.drop_table("universe_history")
    op.drop_index("ix_pit_observations_instrument_field", table_name="pit_observations")
    op.drop_index("ix_pit_observations_field_time", table_name="pit_observations")
    op.drop_table("pit_observations")
    op.drop_table("market_data_sources")
