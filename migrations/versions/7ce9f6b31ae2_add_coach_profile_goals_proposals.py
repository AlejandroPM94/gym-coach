"""add coach profile goals and proposals

Revision ID: 7ce9f6b31ae2
Revises: 323df06d1e7a
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7ce9f6b31ae2"
down_revision: str | None = "323df06d1e7a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "athlete_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("profile_key", sa.String(length=64), nullable=False),
        sa.Column("experience_level", sa.String(length=32), nullable=False),
        sa.Column("training_days_per_week", sa.Integer(), nullable=False),
        sa.Column("session_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("equipment", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("preferences", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_athlete_profiles")),
        sa.UniqueConstraint("profile_key", name=op.f("uq_athlete_profiles_profile_key")),
    )
    op.create_table(
        "training_goals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("goal_type", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("target_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("supersedes_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["athlete_profiles.id"],
            name=op.f("fk_training_goals_profile_id_athlete_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["training_goals.id"],
            name=op.f("fk_training_goals_supersedes_id_training_goals"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_training_goals")),
        sa.UniqueConstraint("profile_id", "version", name=op.f("uq_training_goals_profile_id")),
    )
    op.create_table(
        "coach_proposals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("proposal_data", sa.JSON(), nullable=False),
        sa.Column("evidence_data", sa.JSON(), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["athlete_profiles.id"],
            name=op.f("fk_coach_proposals_profile_id_athlete_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coach_proposals")),
    )


def downgrade() -> None:
    op.drop_table("coach_proposals")
    op.drop_table("training_goals")
    op.drop_table("athlete_profiles")
