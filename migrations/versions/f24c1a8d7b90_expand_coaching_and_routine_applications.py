"""expand coaching profile and routine applications

Revision ID: f24c1a8d7b90
Revises: e15f7c9b4a20
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f24c1a8d7b90"
down_revision: str | None = "e15f7c9b4a20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "athlete_profiles", "experience_level", existing_type=sa.String(32), nullable=True
    )
    columns = (
        sa.Column("birth_year", sa.Integer()),
        sa.Column("sex_for_energy_equation", sa.String(16)),
        sa.Column("height_cm", sa.Numeric(6, 2)),
        sa.Column("occupation_activity", sa.String(32)),
        sa.Column("average_daily_steps", sa.Integer()),
        sa.Column("sleep_hours", sa.Float()),
        sa.Column("sleep_quality", sa.Integer()),
        sa.Column("stress_level", sa.Integer()),
        sa.Column("dietary_pattern", sa.String(64)),
        sa.Column("dietary_restrictions", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("food_allergies", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("nutrition_preferences", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("nutrition_tracking_preference", sa.String(32)),
        sa.Column("health_conditions", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("medications_affecting_training", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("lifestyle_reviewed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("nutrition_reviewed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("health_reviewed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    for column in columns:
        op.add_column("athlete_profiles", column)
    op.create_table(
        "athlete_measurements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("measured_on", sa.Date(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(6, 2)),
        sa.Column("waist_cm", sa.Numeric(6, 2)),
        sa.Column("body_fat_percent", sa.Numeric(5, 2)),
        sa.Column("body_fat_method", sa.String(64)),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("user_confirmed", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["athlete_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "measured_on"),
    )
    op.create_table(
        "athlete_check_ins",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("checked_on", sa.Date(), nullable=False),
        sa.Column("sleep_quality", sa.Integer()),
        sa.Column("stress_level", sa.Integer()),
        sa.Column("energy_level", sa.Integer()),
        sa.Column("hunger_level", sa.Integer()),
        sa.Column("soreness_level", sa.Integer()),
        sa.Column("training_adherence", sa.Integer()),
        sa.Column("nutrition_adherence", sa.Integer()),
        sa.Column("notes", sa.Text()),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("user_confirmed", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["athlete_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "checked_on"),
    )
    op.create_table(
        "routine_applications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("proposal_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("proposal_hash", sa.String(64), nullable=False),
        sa.Column("confirmation_token_hash", sa.String(64), nullable=False),
        sa.Column("source_routine_hash", sa.String(64)),
        sa.Column("result_routine_ids", sa.JSON(), nullable=False),
        sa.Column("error_type", sa.String(128)),
        sa.Column(
            "prepared_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["proposal_id"], ["coach_proposals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposal_id"),
    )


def downgrade() -> None:
    op.drop_table("routine_applications")
    op.drop_table("athlete_check_ins")
    op.drop_table("athlete_measurements")
    for name in reversed(
        (
            "birth_year",
            "sex_for_energy_equation",
            "height_cm",
            "occupation_activity",
            "average_daily_steps",
            "sleep_hours",
            "sleep_quality",
            "stress_level",
            "dietary_pattern",
            "dietary_restrictions",
            "food_allergies",
            "nutrition_preferences",
            "nutrition_tracking_preference",
            "health_conditions",
            "medications_affecting_training",
            "lifestyle_reviewed",
            "nutrition_reviewed",
            "health_reviewed",
        )
    ):
        op.drop_column("athlete_profiles", name)
    op.execute(
        sa.text(
            "UPDATE athlete_profiles SET experience_level = 'beginner' "
            "WHERE experience_level IS NULL"
        )
    )
    op.alter_column(
        "athlete_profiles", "experience_level", existing_type=sa.String(32), nullable=False
    )
