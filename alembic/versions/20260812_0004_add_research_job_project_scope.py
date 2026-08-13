"""Add project scope to research jobs.

Revision ID: 20260812_0004
Revises: 20260812_0003
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260812_0004"
down_revision: str | None = "20260812_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_jobs",
        sa.Column(
            "project_id",
            sa.String(length=128),
            server_default="local",
            nullable=False,
        ),
    )
    op.create_index("ix_research_jobs_project_id", "research_jobs", ["project_id"])
    op.alter_column("research_jobs", "project_id", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_research_jobs_project_id", table_name="research_jobs")
    op.drop_column("research_jobs", "project_id")
