"""Normalized Samsung Health daily snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "e94b2c61b302"
down_revision = "d83a1b50a201"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "health_daily",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("timezone", sa.String(100), primary_key=True),
        sa.Column("source", sa.String(40), primary_key=True),
        sa.Column("steps", sa.Integer()),
        sa.Column("sleep_session_minutes", sa.Numeric(8, 2)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("health_daily")
