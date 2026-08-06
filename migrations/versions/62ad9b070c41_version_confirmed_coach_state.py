"""version confirmed coach state

Revision ID: 62ad9b070c41
Revises: 7ce9f6b31ae2
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "62ad9b070c41"
down_revision: str | None = "7ce9f6b31ae2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "athlete_profiles",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_table(
        "athlete_profile_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("profile_data", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("user_confirmed", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["athlete_profiles.id"],
            name=op.f("fk_athlete_profile_versions_profile_id_athlete_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_athlete_profile_versions")),
        sa.UniqueConstraint(
            "profile_id",
            "version",
            name=op.f("uq_athlete_profile_versions_profile_id"),
        ),
    )
    op.execute(
        """
        INSERT INTO athlete_profile_versions
            (id, profile_id, version, profile_data, source, user_confirmed)
        SELECT
            id,
            id,
            1,
            json_build_object(
                'experience_level', experience_level,
                'training_days_per_week', training_days_per_week,
                'session_duration_minutes', session_duration_minutes,
                'equipment', equipment,
                'limitations', limitations,
                'preferences', preferences
            ),
            'migration',
            false
        FROM athlete_profiles
        """
    )
    op.add_column(
        "training_goals",
        sa.Column("source", sa.String(length=32), server_default="legacy", nullable=False),
    )
    op.add_column(
        "training_goals",
        sa.Column("user_confirmed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("training_goals", "user_confirmed")
    op.drop_column("training_goals", "source")
    op.drop_table("athlete_profile_versions")
    op.drop_column("athlete_profiles", "version")
