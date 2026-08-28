"""Make agent provider credentials provider-global (independent of agent).

Revision ID: 20260827_0024
Revises: 20260827_0023
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260827_0024"
down_revision: str | None = "20260827_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_providers",
        sa.Column("provider", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False, server_default="builtin"),
        sa.Column("base_url", sa.String(255), nullable=True),
        sa.Column("api_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    # 把旧 (agent, provider) 凭据去重迁移为 provider 级：优先带 key、取最新。
    op.execute(
        """
        INSERT INTO agent_providers (provider, kind, base_url, api_key, updated_at)
        SELECT DISTINCT ON (provider)
               provider, kind, base_url, api_key, updated_at
        FROM agent_provider_credentials
        ORDER BY provider,
                 (api_key <> '') DESC,
                 updated_at DESC
        """
    )
    op.drop_table("agent_provider_credentials")


def downgrade() -> None:
    op.create_table(
        "agent_provider_credentials",
        sa.Column("agent", sa.String(16), primary_key=True),
        sa.Column("provider", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False, server_default="builtin"),
        sa.Column("base_url", sa.String(255), nullable=True),
        sa.Column("api_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        """
        INSERT INTO agent_provider_credentials (agent, provider, kind, base_url, api_key, updated_at)
        SELECT 'pi', provider, kind, base_url, api_key, updated_at
        FROM agent_providers
        """
    )
    op.drop_table("agent_providers")
