"""Add agent provider credentials and active agent config tables.

Revision ID: 20260827_0023
Revises: 20260826_0022
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260827_0023"
down_revision: str | None = "20260826_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_provider_credentials",
        sa.Column("agent", sa.String(16), primary_key=True),
        sa.Column("provider", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False, server_default="builtin"),
        sa.Column("base_url", sa.String(255), nullable=True),
        sa.Column("api_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "agent_config",
        sa.Column("id", sa.String(32), primary_key=True, default="default"),
        sa.Column("active_agent", sa.String(16), nullable=False, server_default="pi"),
        sa.Column("active_provider", sa.String(64), nullable=False, server_default=""),
        sa.Column("active_model", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("agent_config")
    op.drop_table("agent_provider_credentials")
