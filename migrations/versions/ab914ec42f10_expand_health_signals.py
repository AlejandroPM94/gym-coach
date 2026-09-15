"""Expand normalized Health Connect signals."""

import sqlalchemy as sa
from alembic import op

revision = "ab914ec42f10"
down_revision = "f47c3d92a105"
branch_labels = None
depends_on = None

DAILY_COLUMNS = (
    sa.Column("sleep_asleep_minutes", sa.Numeric(8, 2)),
    sa.Column("sleep_awake_minutes", sa.Numeric(8, 2)),
    sa.Column("sleep_light_minutes", sa.Numeric(8, 2)),
    sa.Column("sleep_deep_minutes", sa.Numeric(8, 2)),
    sa.Column("sleep_rem_minutes", sa.Numeric(8, 2)),
    sa.Column("sleep_session_count", sa.Integer()),
    sa.Column("main_sleep_start_at", sa.DateTime(timezone=True)),
    sa.Column("main_sleep_end_at", sa.DateTime(timezone=True)),
    sa.Column("exercise_session_count", sa.Integer()),
    sa.Column("exercise_minutes", sa.Numeric(8, 2)),
    sa.Column("exercise_minutes_by_type", sa.JSON()),
    sa.Column("distance_meters", sa.Numeric(12, 2)),
    sa.Column("total_energy_kcal", sa.Numeric(10, 2)),
    sa.Column("heart_rate_sample_count", sa.Integer()),
    sa.Column("mean_heart_rate_bpm", sa.Numeric(6, 2)),
    sa.Column("min_heart_rate_bpm", sa.Integer()),
    sa.Column("max_heart_rate_bpm", sa.Integer()),
    sa.Column("resting_heart_rate_bpm", sa.Numeric(6, 2)),
    sa.Column("hrv_rmssd_ms", sa.Numeric(8, 2)),
    sa.Column("oxygen_saturation_sample_count", sa.Integer()),
    sa.Column("mean_oxygen_saturation_percent", sa.Numeric(6, 2)),
    sa.Column("min_oxygen_saturation_percent", sa.Numeric(6, 2)),
    sa.Column("vo2_max_ml_min_kg", sa.Numeric(6, 2)),
)

BODY_COLUMNS = (
    sa.Column("lean_body_mass_kg", sa.Numeric(6, 2)),
    sa.Column("body_water_mass_kg", sa.Numeric(6, 2)),
    sa.Column("bone_mass_kg", sa.Numeric(5, 2)),
    sa.Column("basal_metabolic_rate_kcal", sa.Numeric(8, 2)),
)


def upgrade() -> None:
    for column in DAILY_COLUMNS:
        op.add_column("health_daily", column)
    for column in BODY_COLUMNS:
        op.add_column("health_body_measurements", column)


def downgrade() -> None:
    for column in reversed(BODY_COLUMNS):
        op.drop_column("health_body_measurements", column.name)
    for column in reversed(DAILY_COLUMNS):
        op.drop_column("health_daily", column.name)
