"""Normalized body measurements from Health Connect."""

import sqlalchemy as sa
from alembic import op

revision = "f47c3d92a105"
down_revision = "e94b2c61b302"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "health_body_measurements",
        sa.Column("source", sa.String(40), primary_key=True),
        sa.Column("external_id", sa.UUID(), primary_key=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("measured_on", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(100), nullable=False),
        sa.Column("weight_kg", sa.Numeric(6, 2), nullable=False),
        sa.Column("body_fat_percent", sa.Numeric(5, 2)),
        sa.Column("body_fat_method", sa.String(64)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_health_body_measurements_measured_on",
        "health_body_measurements",
        ["measured_on"],
    )


def downgrade() -> None:
    op.drop_table("health_body_measurements")
