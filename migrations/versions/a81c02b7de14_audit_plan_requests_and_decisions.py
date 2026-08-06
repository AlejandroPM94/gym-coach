"""audit plan requests and decisions

Revision ID: a81c02b7de14
Revises: 62ad9b070c41
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a81c02b7de14"
down_revision: str | None = "62ad9b070c41"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "coach_proposals",
        sa.Column(
            "request_source",
            sa.String(length=32),
            server_default="legacy",
            nullable=False,
        ),
    )
    op.add_column(
        "coach_proposals",
        sa.Column("user_requested", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "coach_proposals",
        sa.Column("decision_source", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "coach_proposals",
        sa.Column("decision_user_confirmed", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("coach_proposals", "decision_user_confirmed")
    op.drop_column("coach_proposals", "decision_source")
    op.drop_column("coach_proposals", "user_requested")
    op.drop_column("coach_proposals", "request_source")
