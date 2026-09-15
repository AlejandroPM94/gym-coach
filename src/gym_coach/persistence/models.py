from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gym_coach.db import Base


class NutritionRecord(Base):
    """Immutable confirmed nutrition records; request UUID provides retry safety."""

    __tablename__ = "nutrition_records"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    request: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    user_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="hevy")
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="full_snapshot")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_type: Mapped[str | None] = mapped_column(String(128))


class ExternalRecordMixin:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_sync_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sync_runs.id")
    )
    last_seen_sync_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sync_runs.id"), nullable=False
    )


class HevyUser(ExternalRecordMixin, Base):
    __tablename__ = "hevy_users"

    name: Mapped[str | None] = mapped_column(String(255))
    profile_url: Mapped[str | None] = mapped_column(Text)


class ExerciseTemplate(ExternalRecordMixin, Base):
    __tablename__ = "exercise_templates"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    exercise_type: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_muscle_group: Mapped[str] = mapped_column(String(64), nullable=False)
    equipment: Mapped[str | None] = mapped_column(String(64))
    is_custom: Mapped[bool | None] = mapped_column(Boolean)
    secondary_muscles: Mapped[list["ExerciseTemplateSecondaryMuscle"]] = relationship(
        cascade="all, delete-orphan", order_by="ExerciseTemplateSecondaryMuscle.position"
    )


class ExerciseTemplateSecondaryMuscle(Base):
    __tablename__ = "exercise_template_secondary_muscles"
    __table_args__ = (UniqueConstraint("template_id", "position"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exercise_templates.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    muscle_group: Mapped[str] = mapped_column(String(64), nullable=False)


class Routine(ExternalRecordMixin, Base):
    __tablename__ = "routines"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    folder_id: Mapped[int | None] = mapped_column(Integer)
    exercises: Mapped[list["RoutineExercise"]] = relationship(
        cascade="all, delete-orphan", order_by="RoutineExercise.position"
    )


class RoutineExercise(Base):
    __tablename__ = "routine_exercises"
    __table_args__ = (UniqueConstraint("routine_id", "position"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    routine_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("routines.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    exercise_template_external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    superset_id: Mapped[int | None] = mapped_column(Integer)
    rest_seconds: Mapped[int | None] = mapped_column(Integer)
    sets: Mapped[list["RoutineSet"]] = relationship(
        cascade="all, delete-orphan", order_by="RoutineSet.position"
    )


class RoutineSet(Base):
    __tablename__ = "routine_sets"
    __table_args__ = (UniqueConstraint("routine_exercise_id", "position"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    routine_exercise_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("routine_exercises.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    set_type: Mapped[str | None] = mapped_column(String(32))
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    reps: Mapped[int | None] = mapped_column(Integer)
    distance_meters: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    custom_metric: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    rep_range_start: Mapped[int | None] = mapped_column(Integer)
    rep_range_end: Mapped[int | None] = mapped_column(Integer)


class RoutineVersion(Base):
    """Immutable provider prescription captured during synchronization."""

    __tablename__ = "routine_versions"
    __table_args__ = (UniqueConstraint("routine_external_id", "content_hash"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    routine_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class Workout(ExternalRecordMixin, Base):
    __tablename__ = "workouts"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    routine_external_id: Mapped[str | None] = mapped_column(String(128))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    routine_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("routine_versions.id")
    )
    exercises: Mapped[list["WorkoutExercise"]] = relationship(
        cascade="all, delete-orphan", order_by="WorkoutExercise.position"
    )


class WorkoutExercise(Base):
    __tablename__ = "workout_exercises"
    __table_args__ = (UniqueConstraint("workout_id", "position"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workout_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("workouts.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    exercise_template_external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    superset_id: Mapped[int | None] = mapped_column(Integer)
    sets: Mapped[list["WorkoutSet"]] = relationship(
        cascade="all, delete-orphan", order_by="WorkoutSet.position"
    )


class WorkoutSet(Base):
    __tablename__ = "workout_sets"
    __table_args__ = (UniqueConstraint("workout_exercise_id", "position"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workout_exercise_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("workout_exercises.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    set_type: Mapped[str | None] = mapped_column(String(32))
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    reps: Mapped[int | None] = mapped_column(Integer)
    distance_meters: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    rpe: Mapped[float | None] = mapped_column(Float)
    custom_metric: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))


class AutomationCursor(Base):
    __tablename__ = "automation_cursors"

    stream: Mapped[str] = mapped_column(String(64), primary_key=True)
    cursor_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class WorkoutReview(Base):
    __tablename__ = "workout_reviews"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    workout_external_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AthleteProfile(Base):
    __tablename__ = "athlete_profiles"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    profile_key: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, default="default"
    )
    experience_level: Mapped[str | None] = mapped_column(String(32))
    birth_year: Mapped[int | None] = mapped_column(Integer)
    sex_for_energy_equation: Mapped[str | None] = mapped_column(String(16))
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    training_days_per_week: Mapped[int] = mapped_column(Integer, nullable=False)
    session_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    equipment: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    limitations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    preferences: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    limitations_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    preferences_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    occupation_activity: Mapped[str | None] = mapped_column(String(32))
    average_daily_steps: Mapped[int | None] = mapped_column(Integer)
    sleep_hours: Mapped[float | None] = mapped_column(Float)
    sleep_quality: Mapped[int | None] = mapped_column(Integer)
    stress_level: Mapped[int | None] = mapped_column(Integer)
    dietary_pattern: Mapped[str | None] = mapped_column(String(64))
    dietary_restrictions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    food_allergies: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    nutrition_preferences: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    nutrition_tracking_preference: Mapped[str | None] = mapped_column(String(32))
    health_conditions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    medications_affecting_training: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    lifestyle_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    nutrition_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    health_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AthleteProfileVersion(Base):
    __tablename__ = "athlete_profile_versions"
    __table_args__ = (UniqueConstraint("profile_id", "version"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("athlete_profiles.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_data: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    user_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TrainingGoal(Base):
    __tablename__ = "training_goals"
    __table_args__ = (UniqueConstraint("profile_id", "version"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("athlete_profiles.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    goal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    target_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="cli")
    user_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("training_goals.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CoachProposal(Base):
    __tablename__ = "coach_proposals"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("athlete_profiles.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    proposal_data: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    evidence_data: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    request_source: Mapped[str] = mapped_column(String(32), nullable=False, default="pydanticai")
    user_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_source: Mapped[str | None] = mapped_column(String(32))
    decision_user_confirmed: Mapped[bool | None] = mapped_column(Boolean)


class AthleteMeasurement(Base):
    __tablename__ = "athlete_measurements"
    __table_args__ = (UniqueConstraint("profile_id", "measured_on"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("athlete_profiles.id", ondelete="CASCADE"), nullable=False
    )
    measured_on: Mapped[date] = mapped_column(Date, nullable=False)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    waist_cm: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    body_fat_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    body_fat_method: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    user_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AthleteCheckIn(Base):
    __tablename__ = "athlete_check_ins"
    __table_args__ = (UniqueConstraint("profile_id", "checked_on"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("athlete_profiles.id", ondelete="CASCADE"), nullable=False
    )
    checked_on: Mapped[date] = mapped_column(Date, nullable=False)
    sleep_quality: Mapped[int | None] = mapped_column(Integer)
    stress_level: Mapped[int | None] = mapped_column(Integer)
    energy_level: Mapped[int | None] = mapped_column(Integer)
    hunger_level: Mapped[int | None] = mapped_column(Integer)
    soreness_level: Mapped[int | None] = mapped_column(Integer)
    training_adherence: Mapped[int | None] = mapped_column(Integer)
    nutrition_adherence: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    user_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RoutineApplication(Base):
    __tablename__ = "routine_applications"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    proposal_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("coach_proposals.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="prepared")
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmation_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_routine_hash: Mapped[str | None] = mapped_column(String(64))
    result_routine_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    error_type: Mapped[str | None] = mapped_column(String(128))
    prepared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TrackingRecord(Base):
    """Append-only target versions and confirmed diary coverage."""

    __tablename__ = "tracking_records"
    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    user_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class HealthDaily(Base):
    __tablename__ = "health_daily"
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    timezone: Mapped[str] = mapped_column(String(100), primary_key=True)
    source: Mapped[str] = mapped_column(String(40), primary_key=True)
    steps: Mapped[int | None] = mapped_column(Integer)
    sleep_session_minutes: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    sleep_asleep_minutes: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    sleep_awake_minutes: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    sleep_light_minutes: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    sleep_deep_minutes: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    sleep_rem_minutes: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    sleep_session_count: Mapped[int | None] = mapped_column(Integer)
    main_sleep_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    main_sleep_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exercise_session_count: Mapped[int | None] = mapped_column(Integer)
    exercise_minutes: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    exercise_minutes_by_type: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    distance_meters: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    total_energy_kcal: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    heart_rate_sample_count: Mapped[int | None] = mapped_column(Integer)
    mean_heart_rate_bpm: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    min_heart_rate_bpm: Mapped[int | None] = mapped_column(Integer)
    max_heart_rate_bpm: Mapped[int | None] = mapped_column(Integer)
    resting_heart_rate_bpm: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    hrv_rmssd_ms: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    oxygen_saturation_sample_count: Mapped[int | None] = mapped_column(Integer)
    mean_oxygen_saturation_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    min_oxygen_saturation_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    vo2_max_ml_min_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class HealthBodyMeasurement(Base):
    __tablename__ = "health_body_measurements"

    source: Mapped[str] = mapped_column(String(40), primary_key=True)
    external_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    measured_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    body_fat_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    body_fat_method: Mapped[str | None] = mapped_column(String(64))
    lean_body_mass_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    body_water_mass_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    bone_mass_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    basal_metabolic_rate_kcal: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
