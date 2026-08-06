from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MCPPublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ComponentStatus(MCPPublicModel):
    status: Literal["available", "unavailable", "not_configured"]
    detail: str


class SystemStatus(MCPPublicModel):
    application: str = "gym-coach"
    version: str
    backend_status: Literal["healthy", "degraded"]
    read_only: bool = True
    hevy: ComponentStatus
    postgres: ComponentStatus


class HevyConnectionStatus(MCPPublicModel):
    configured: bool
    accessible: bool
    status: Literal["available", "unavailable", "not_configured"]
    detail: str


class AthleteGoal(MCPPublicModel):
    goal_type: str
    description: str
    priority: int
    target_date: date | None = None


class AthleteSummary(MCPPublicModel):
    source: Literal["athlete_profile", "hevy_sync", "none"]
    profile_complete: bool
    hevy_data_available: bool
    experience_level: str | None = None
    training_days_per_week: int | None = None
    session_duration_minutes: int | None = None
    equipment: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    goals: list[AthleteGoal] = Field(default_factory=list)
    pending_fields: list[str] = Field(default_factory=list)


class RoutineSummary(MCPPublicModel):
    external_id: str
    title: str
    folder_id: int | None = None
    position: int = Field(ge=1)
    exercise_count: int = Field(ge=0)


class RoutineList(MCPPublicModel):
    count: int = Field(ge=0)
    routines: list[RoutineSummary]


class PlannedSet(MCPPublicModel):
    position: int = Field(ge=1)
    set_type: str | None = None
    weight_kg: str | None = None
    reps: int | None = None
    rep_range_start: int | None = None
    rep_range_end: int | None = None
    distance_meters: str | None = None
    duration_seconds: int | None = None


class PlannedExercise(MCPPublicModel):
    position: int = Field(ge=1)
    exercise_template_external_id: str
    title: str
    notes: str | None = None
    rest_seconds: int | None = None
    superset_id: int | None = None
    sets: list[PlannedSet]


class TrainingRoutine(MCPPublicModel):
    external_id: str
    title: str
    folder_id: int | None = None
    updated_at: datetime | None = None
    exercises: list[PlannedExercise]


class WorkoutSummary(MCPPublicModel):
    external_id: str
    title: str
    start_time: datetime
    end_time: datetime
    routine_external_id: str | None = None
    exercise_count: int = Field(ge=0)


class RecentWorkouts(MCPPublicModel):
    requested_limit: int
    count: int = Field(ge=0)
    workouts: list[WorkoutSummary]


class CompletedSet(MCPPublicModel):
    position: int = Field(ge=1)
    set_type: str | None = None
    weight_kg: str | None = None
    reps: int | None = None
    distance_meters: str | None = None
    duration_seconds: int | None = None
    rpe: float | None = None


class CompletedExercise(MCPPublicModel):
    position: int = Field(ge=1)
    exercise_template_external_id: str
    title: str
    notes: str | None = None
    superset_id: int | None = None
    sets: list[CompletedSet]


class TrainingWorkout(MCPPublicModel):
    external_id: str
    title: str
    description: str | None = None
    routine_external_id: str | None = None
    start_time: datetime
    end_time: datetime
    exercises: list[CompletedExercise]


class ExerciseTemplateSummary(MCPPublicModel):
    external_id: str
    title: str
    exercise_type: str
    primary_muscle_group: str
    secondary_muscle_groups: list[str]
    equipment: str | None = None
    is_custom: bool | None = None


class ExerciseTemplateSearchResults(MCPPublicModel):
    query: str
    requested_limit: int
    count: int = Field(ge=0)
    results: list[ExerciseTemplateSummary]
