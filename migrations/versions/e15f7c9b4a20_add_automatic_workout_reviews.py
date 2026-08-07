"""add automatic workout reviews

Revision ID: e15f7c9b4a20
Revises: c934b2e1f609
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e15f7c9b4a20"
down_revision: str | None = "c934b2e1f609"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "automation_cursors",
        sa.Column("stream", sa.String(length=64), nullable=False),
        sa.Column("cursor_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("stream"),
    )
    op.create_table(
        "workout_reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workout_external_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workout_external_id"),
    )


def downgrade() -> None:
    op.drop_table("workout_reviews")
    op.drop_table("automation_cursors")
