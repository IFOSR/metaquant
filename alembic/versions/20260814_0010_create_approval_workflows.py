"""Create approval workflows for two-person governance.

Revision ID: 20260814_0010
Revises: 20260814_0009
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0010"
down_revision: str | None = "20260814_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approval_workflows",
        sa.Column("workflow_id", sa.String(64), primary_key=True),
        sa.Column("subject_hash", sa.String(64), nullable=False),
        sa.Column("subject_kind", sa.String(32), nullable=False),
        sa.Column("required_approvals", sa.Integer(), nullable=False),
        sa.Column("decisions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_approval_workflows_subject_hash",
        "approval_workflows",
        ["subject_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_approval_workflows_subject_hash", table_name="approval_workflows")
    op.drop_table("approval_workflows")
