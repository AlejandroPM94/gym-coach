from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ProfileItem = Annotated[str, Field(min_length=1, max_length=500)]
EvidenceId = Annotated[
    str,
    Field(min_length=3, max_length=255, pattern=r"^[a-z0-9_.:-]+$"),
]


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
    version: int = Field(ge=1)
    goal_type: str
    description: str
    priority: int
    target_date: date | None = None


class AthleteSummary(MCPPublicModel):
    source: Literal["athlete_profile", "hevy_sync", "none"]
    profile_complete: bool
    profile_version: int | None = None
    hevy_data_available: bool
    experience_level: str | None = None
    training_days_per_week: int | None = None
    session_duration_minutes: int | None = None
    equipment: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    goals: list[AthleteGoal] = Field(default_factory=list)
    pending_fields: list[str] = Field(default_factory=list)


class AthleteProfileUpdate(MCPPublicModel):
    experience_level: Literal["beginner", "intermediate", "advanced"]
    training_days_per_week: Annotated[int, Field(ge=1, le=7)]
    session_duration_minutes: Annotated[int | None, Field(ge=15, le=300)] = None
    equipment: list[ProfileItem] = Field(default_factory=list, max_length=50)
    limitations: list[ProfileItem] = Field(default_factory=list, max_length=20)
    preferences: list[ProfileItem] = Field(default_factory=list, max_length=30)


class TrainingGoalUpdate(MCPPublicModel):
    goal_type: Literal["strength", "hypertrophy", "endurance", "health", "skill", "other"]
    description: Annotated[str, Field(min_length=3, max_length=1000)]
    priority: Annotated[int, Field(ge=1, le=5)] = 1
    target_date: date | None = None


class OnboardingStatus(MCPPublicModel):
    profile_present: bool
    profile_version: int | None = None
    active_goal_count: int = Field(ge=0)
    pending_fields: list[str]
    ready_for_training_analysis: bool
    next_action: str


class ProfileMutationResult(MCPPublicModel):
    saved: bool = True
    profile_version: int = Field(ge=1)
    user_confirmation_recorded: bool = True
    message: str


class GoalMutationResult(MCPPublicModel):
    saved: bool = True
    goal_version: int = Field(ge=1)
    status: Literal["active"] = "active"
    user_confirmation_recorded: bool = True
    message: str


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


class AdherenceSummary(MCPPublicModel):
    window_days: int = Field(ge=1)
    target_sessions_per_week: str
    expected_sessions: str
    completed_sessions: int = Field(ge=0)
    adherence_percent: str
    matched_routine_sessions: int = Field(ge=0)


class StagnationSummary(MCPPublicModel):
    exercise_template_external_id: str
    is_stalled: bool
    reason: str
    qualifying_sessions: int = Field(ge=0)
    span_days: int = Field(ge=0)
    improvement_percent: str | None = None


class TrainingMetrics(MCPPublicModel):
    evidence_id: str
    period_start: datetime
    period_end: datetime
    window_days: int = Field(ge=1)
    workouts: int = Field(ge=0)
    total_reps: int = Field(ge=0)
    total_volume_kg_reps: str
    adherence: AdherenceSummary
    stalled_exercises: list[StagnationSummary]


class ExerciseSessionSummary(MCPPublicModel):
    workout_external_id: str
    performed_at: datetime
    total_reps: int = Field(ge=0)
    volume_kg_reps: str
    best_e1rm_kg: str | None = None
    qualifying_sets: int = Field(ge=0)


class ExerciseProgressReport(MCPPublicModel):
    evidence_id: str
    exercise_template_external_id: str
    period_start: datetime
    period_end: datetime
    latest_e1rm_kg: str | None = None
    previous_e1rm_kg: str | None = None
    e1rm_change_kg: str | None = None
    e1rm_change_percent: str | None = None
    stagnation: StagnationSummary
    sessions: list[ExerciseSessionSummary]


class ProposedPlanSet(MCPPublicModel):
    set_type: Literal["warmup", "normal", "drop", "failure"] = "normal"
    reps_min: int = Field(ge=1, le=100)
    reps_max: int = Field(ge=1, le=100)
    target_rpe: float | None = Field(default=None, ge=1, le=10)
    load_guidance: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_range(self) -> "ProposedPlanSet":
        if self.reps_max < self.reps_min:
            raise ValueError("reps_max must be greater than or equal to reps_min")
        return self


class ProposedPlanExercise(MCPPublicModel):
    exercise_template_external_id: str | None = None
    title: str = Field(min_length=1, max_length=255)
    rest_seconds: int = Field(ge=0, le=900)
    sets: list[ProposedPlanSet] = Field(min_length=1, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)


class ProposedPlanWorkout(MCPPublicModel):
    title: str = Field(min_length=1, max_length=255)
    exercises: list[ProposedPlanExercise] = Field(min_length=1, max_length=30)


class TrainingPlanProposalInput(MCPPublicModel):
    kind: Literal["new_routine", "routine_update", "progression"]
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=4000)
    evidence_ids: list[EvidenceId] = Field(min_length=1, max_length=100)
    source_routine_id: str | None = Field(default=None, max_length=128)
    workouts: list[ProposedPlanWorkout] = Field(min_length=1, max_length=7)


class TrainingPlanProposal(MCPPublicModel):
    proposal_id: UUID
    status: Literal["draft", "approved", "rejected"]
    created_at: datetime
    decided_at: datetime | None = None
    plan: TrainingPlanProposalInput
    applied_to_hevy: bool = False


class PlanComparisonSide(MCPPublicModel):
    title: str
    workout_count: int = Field(ge=0)
    exercise_count: int = Field(ge=0)
    set_count: int = Field(ge=0)


class TrainingPlanComparison(MCPPublicModel):
    proposal_id: UUID
    status: Literal["draft", "approved", "rejected"]
    current: PlanComparisonSide | None = None
    proposed: PlanComparisonSide
    rationale: str
    changes_are_applied: bool = False


class PlanDecisionResult(MCPPublicModel):
    proposal_id: UUID
    status: Literal["approved", "rejected"]
    user_confirmation_recorded: bool = True
    applied_to_hevy: bool = False
    message: str
