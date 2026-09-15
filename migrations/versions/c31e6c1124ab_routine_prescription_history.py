"""Capture immutable routine prescriptions and link workouts."""

import sqlalchemy as sa
from alembic import op

revision = "c31e6c1124ab"
down_revision = "ab914ec42f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "routine_versions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("routine_external_id", sa.String(128), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("routine_external_id", "content_hash"),
    )
    op.create_index(
        "ix_routine_versions_routine_external_id",
        "routine_versions",
        ["routine_external_id"],
    )
    op.add_column("workouts", sa.Column("routine_version_id", sa.UUID()))
    op.create_foreign_key(
        "fk_workouts_routine_version_id",
        "workouts",
        "routine_versions",
        ["routine_version_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_workouts_routine_version_id", "workouts", type_="foreignkey")
    op.drop_column("workouts", "routine_version_id")
    op.drop_table("routine_versions")
