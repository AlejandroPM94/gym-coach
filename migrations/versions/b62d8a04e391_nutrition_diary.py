"""Immutable personal nutrition catalogue and diary."""

import sqlalchemy as sa
from alembic import op

revision = "b62d8a04e391"
down_revision = "f24c1a8d7b90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nutrition_records",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("user_confirmed", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_nutrition_records_kind", "nutrition_records", ["kind"])
    op.create_index("ix_nutrition_records_consumed_at", "nutrition_records", ["consumed_at"])


def downgrade() -> None:
    op.drop_table("nutrition_records")
