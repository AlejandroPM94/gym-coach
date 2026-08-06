"""review profile safety and preferences

Revision ID: c934b2e1f609
Revises: a81c02b7de14
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c934b2e1f609"
down_revision: str | None = "a81c02b7de14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "athlete_profiles",
        sa.Column("limitations_reviewed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "athlete_profiles",
        sa.Column("preferences_reviewed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("athlete_profiles", "preferences_reviewed")
    op.drop_column("athlete_profiles", "limitations_reviewed")
