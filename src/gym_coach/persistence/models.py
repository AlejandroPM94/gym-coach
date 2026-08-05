from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
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


class Workout(ExternalRecordMixin, Base):
    __tablename__ = "workouts"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    routine_external_id: Mapped[str | None] = mapped_column(String(128))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
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


class AthleteProfile(Base):
    __tablename__ = "athlete_profiles"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    profile_key: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, default="default"
    )
    experience_level: Mapped[str] = mapped_column(String(32), nullable=False)
    training_days_per_week: Mapped[int] = mapped_column(Integer, nullable=False)
    session_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    equipment: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    limitations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    preferences: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
