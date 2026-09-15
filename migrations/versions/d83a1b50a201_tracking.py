"""Versioned targets and diary completeness."""

import sqlalchemy as sa
from alembic import op

revision = "d83a1b50a201"
down_revision = "b62d8a04e391"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tracking_records",
        sa.Column("sequence", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.UUID(), nullable=False, unique=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("user_confirmed", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_tracking_records_kind", "tracking_records", ["kind"])
    op.create_index("ix_tracking_records_day", "tracking_records", ["day"])


def downgrade() -> None:
    op.drop_table("tracking_records")
