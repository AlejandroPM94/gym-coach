from datetime import date, datetime
from decimal import Decimal
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
    read_only: bool = False
    hevy_writes_guarded: bool = True
    hevy: ComponentStatus
    postgres: ComponentStatus


class HevyConnectionStatus(MCPPublicModel):
    configured: bool
    accessible: bool
    status: Literal["available", "unavailable", "not_configured"]
    detail: str


class HevySyncResult(MCPPublicModel):
    """Summary of a complete, idempotent Hevy-to-PostgreSQL synchronization."""

    status: Literal["succeeded"] = "succeeded"
    run_id: str
    inserted: int = Field(ge=0)
    updated: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    deleted: int = Field(ge=0)


class AthleteGoal(MCPPublicModel):
    evidence_id: EvidenceId
    version: int = Field(ge=1)
    goal_type: str
    description: str
    priority: int
    target_date: date | None = None


class AthleteSummary(MCPPublicModel):
    source: Literal["athlete_profile", "hevy_sync", "none"]
    profile_complete: bool
    profile_version: int | None = None
    profile_evidence_id: EvidenceId | None = None
    hevy_data_available: bool
    experience_level: str | None = None
    birth_year: int | None = None
    sex_for_energy_equation: str | None = None
    height_cm: str | None = None
    training_days_per_week: int | None = None
    session_duration_minutes: int | None = None
    equipment: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    limitations_reviewed: bool = False
    preferences_reviewed: bool = False
    occupation_activity: str | None = None
    average_daily_steps: int | None = None
    sleep_hours: float | None = None
    sleep_quality: int | None = None
    stress_level: int | None = None
    dietary_pattern: str | None = None
    dietary_restrictions: list[str] = Field(default_factory=list)
    food_allergies: list[str] = Field(default_factory=list)
    nutrition_preferences: list[str] = Field(default_factory=list)
    nutrition_tracking_preference: str | None = None
    health_conditions: list[str] = Field(default_factory=list)
    medications_affecting_training: list[str] = Field(default_factory=list)
    lifestyle_reviewed: bool = False
    nutrition_reviewed: bool = False
    health_reviewed: bool = False
    goals: list[AthleteGoal] = Field(default_factory=list)
    pending_fields: list[str] = Field(default_factory=list)


class AthleteProfileUpdate(MCPPublicModel):
    experience_level: Literal["beginner", "intermediate", "advanced"] | None = None
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    sex_for_energy_equation: Literal["female", "male", "unspecified"] = "unspecified"
    height_cm: Decimal | None = Field(default=None, ge=100, le=250)
    training_days_per_week: Annotated[int, Field(ge=1, le=7)]
    session_duration_minutes: Annotated[int | None, Field(ge=15, le=300)] = None
    equipment: list[ProfileItem] = Field(default_factory=list, max_length=50)
    limitations: list[ProfileItem] = Field(default_factory=list, max_length=20)
    preferences: list[ProfileItem] = Field(default_factory=list, max_length=30)
    limitations_reviewed: Literal[True]
    preferences_reviewed: Literal[True]
    occupation_activity: Literal["sedentary", "light", "moderate", "high"] | None = None
    average_daily_steps: int | None = Field(default=None, ge=0, le=100_000)
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    sleep_quality: int | None = Field(default=None, ge=1, le=5)
    stress_level: int | None = Field(default=None, ge=1, le=5)
    dietary_pattern: str | None = Field(default=None, max_length=64)
    dietary_restrictions: list[ProfileItem] = Field(default_factory=list, max_length=30)
    food_allergies: list[ProfileItem] = Field(default_factory=list, max_length=30)
    nutrition_preferences: list[ProfileItem] = Field(default_factory=list, max_length=30)
    nutrition_tracking_preference: Literal["none", "habits", "portions", "calories"] | None = None
    health_conditions: list[ProfileItem] = Field(default_factory=list, max_length=30)
    medications_affecting_training: list[ProfileItem] = Field(default_factory=list, max_length=30)
    lifestyle_reviewed: Literal[True]
    nutrition_reviewed: Literal[True]
    health_reviewed: Literal[True]


class AthleteMeasurementInput(MCPPublicModel):
    measured_on: date
    weight_kg: Decimal | None = Field(default=None, ge=25, le=500)
    waist_cm: Decimal | None = Field(default=None, ge=30, le=300)
    body_fat_percent: Decimal | None = Field(default=None, ge=2, le=70)
    body_fat_method: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def require_measurement(self) -> "AthleteMeasurementInput":
        if self.weight_kg is None and self.waist_cm is None and self.body_fat_percent is None:
            raise ValueError("at least one measurement is required")
        return self


class AthleteMeasurementView(AthleteMeasurementInput):
    measurement_id: UUID
    user_confirmation_recorded: bool = True


class AthleteCheckInInput(MCPPublicModel):
    checked_on: date
    sleep_quality: int | None = Field(default=None, ge=1, le=5)
    stress_level: int | None = Field(default=None, ge=1, le=5)
    energy_level: int | None = Field(default=None, ge=1, le=5)
    hunger_level: int | None = Field(default=None, ge=1, le=5)
    soreness_level: int | None = Field(default=None, ge=1, le=5)
    training_adherence: int | None = Field(default=None, ge=1, le=5)
    nutrition_adherence: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = Field(default=None, max_length=1000)


class AthleteCheckInView(AthleteCheckInInput):
    check_in_id: UUID
    user_confirmation_recorded: bool = True


class TrainingHistoryAssessment(MCPPublicModel):
    evidence_id: EvidenceId
    period_start: datetime | None = None
    period_end: datetime | None = None
    calendar_days: int = Field(ge=0)
    workout_count: int = Field(ge=0)
    active_week_count: int = Field(ge=0)
    distinct_exercise_count: int = Field(ge=0)
    workouts_per_active_week: str
    history_level: Literal["insufficient", "developing", "established", "extensive"]
    confidence: Literal["low", "medium", "high"]
    limitations: list[str]


class CoachingRule(MCPPublicModel):
    rule_id: str
    topic: Literal[
        "resistance_training", "physical_activity", "fat_loss", "protein", "diet_quality"
    ]
    guidance: str
    source_title: str
    source_url: str
    source_year: int
    scope: str


class CoachingAssessment(MCPPublicModel):
    history: TrainingHistoryAssessment
    readiness: Literal["needs_interview", "ready_for_analysis", "needs_professional_clearance"]
    missing_or_unreviewed: list[str]
    priority_questions: list[str]
    latest_weight_kg: str | None = None
    bmi: str | None = None
    resting_energy_kcal: int | None = None
    protein_range_g_per_day: tuple[int, int] | None = None
    nutrition_note: str
    safety_note: str
    applicable_rules: list[CoachingRule]


class TrainingGoalUpdate(MCPPublicModel):
    goal_type: Literal[
        "strength",
        "hypertrophy",
        "fat_loss",
        "body_recomposition",
        "endurance",
        "health",
        "skill",
        "other",
    ]
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
    evidence_id: EvidenceId
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
    reps_min: int | None = Field(default=None, ge=1, le=100)
    reps_max: int | None = Field(default=None, ge=1, le=100)
    duration_seconds_min: int | None = Field(default=None, ge=1, le=7200)
    duration_seconds_max: int | None = Field(default=None, ge=1, le=7200)
    distance_meters_min: Decimal | None = Field(default=None, gt=0, le=100_000)
    distance_meters_max: Decimal | None = Field(default=None, gt=0, le=100_000)
    target_rpe: float | None = Field(default=None, ge=1, le=10)
    load_guidance: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_range(self) -> "ProposedPlanSet":
        ranges = (
            ("reps", self.reps_min, self.reps_max),
            ("duration_seconds", self.duration_seconds_min, self.duration_seconds_max),
            ("distance_meters", self.distance_meters_min, self.distance_meters_max),
        )
        selected = [
            (name, minimum, maximum) for name, minimum, maximum in ranges if minimum or maximum
        ]
        if len(selected) != 1:
            raise ValueError(
                "exactly one of reps, duration_seconds, or distance_meters is required"
            )
        name, minimum, maximum = selected[0]
        if minimum is None or maximum is None:
            raise ValueError(f"{name}_min and {name}_max must be provided together")
        if maximum < minimum:
            raise ValueError(f"{name}_max must be greater than or equal to {name}_min")
        return self


class ProposedPlanExercise(MCPPublicModel):
    exercise_template_external_id: str | None = None
    title: str = Field(min_length=1, max_length=255)
    rest_seconds: int = Field(ge=0, le=900)
    sets: list[ProposedPlanSet] = Field(min_length=1, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)
    superset_group: str | None = Field(
        default=None, min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.:-]+$"
    )


class ProposedPlanWorkout(MCPPublicModel):
    title: str = Field(min_length=1, max_length=255)
    exercises: list[ProposedPlanExercise] = Field(min_length=1, max_length=30)
    optional: bool = False
    location: Literal["gym", "home", "outdoors", "other"] = "gym"
    estimated_duration_minutes: int | None = Field(default=None, ge=5, le=300)

    @model_validator(mode="after")
    def validate_superset_groups(self) -> "ProposedPlanWorkout":
        groups: dict[str, list[int]] = {}
        for index, exercise in enumerate(self.exercises):
            if exercise.superset_group is not None:
                groups.setdefault(exercise.superset_group, []).append(index)
        for group, indexes in groups.items():
            if len(indexes) < 2:
                raise ValueError(f"superset_group {group!r} must contain at least two exercises")
            if indexes != list(range(indexes[0], indexes[-1] + 1)):
                raise ValueError(f"superset_group {group!r} must be contiguous")
        return self


class PlanChangeJustification(MCPPublicModel):
    description: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[EvidenceId] = Field(min_length=1, max_length=30)


class VerifiedPlanEvidence(MCPPublicModel):
    evidence_id: EvidenceId
    category: Literal["profile", "goal", "routine", "metric", "history"]
    description: str
    value: str
    period_start: datetime | None = None
    period_end: datetime | None = None


class TrainingPlanProposalInput(MCPPublicModel):
    kind: Literal["new_routine", "routine_update", "progression"]
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=4000)
    evidence_ids: list[EvidenceId] = Field(min_length=1, max_length=100)
    source_routine_id: str | None = Field(default=None, max_length=128)
    workouts: list[ProposedPlanWorkout] = Field(min_length=1, max_length=7)
    changes: list[PlanChangeJustification] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_change_evidence(self) -> "TrainingPlanProposalInput":
        global_evidence = set(self.evidence_ids)
        missing = {
            evidence_id
            for change in self.changes
            for evidence_id in change.evidence_ids
            if evidence_id not in global_evidence
        }
        if missing:
            raise ValueError("change evidence_ids must also appear in proposal evidence_ids")
        return self


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
    required_workout_count: int = Field(ge=0)
    optional_workout_count: int = Field(ge=0)
    exercise_count: int = Field(ge=0)
    set_count: int = Field(ge=0)
    superset_group_count: int = Field(ge=0, default=0)


class ExercisePlanChange(MCPPublicModel):
    exercise_template_external_id: str
    title: str
    change: Literal["added", "removed", "retained"]
    current_frequency: int = Field(ge=0)
    proposed_frequency: int = Field(ge=0)
    current_sets: int = Field(ge=0)
    proposed_sets: int = Field(ge=0)
    set_delta: int


class MuscleGroupPlanChange(MCPPublicModel):
    muscle_group: str
    current_sets: int = Field(ge=0)
    proposed_sets: int = Field(ge=0)
    set_delta: int


class TrainingPlanComparison(MCPPublicModel):
    proposal_id: UUID
    status: Literal["draft", "approved", "rejected"]
    current: PlanComparisonSide | None = None
    proposed: PlanComparisonSide
    rationale: str
    exercise_changes: list[ExercisePlanChange]
    muscle_group_changes: list[MuscleGroupPlanChange]
    unmatched_current_titles: list[str]
    unmatched_proposed_titles: list[str]
    changes_are_applied: bool = False


class PlanDecisionResult(MCPPublicModel):
    proposal_id: UUID
    status: Literal["approved", "rejected"]
    user_confirmation_recorded: bool = True
    applied_to_hevy: bool = False
    message: str


class RoutineApplicationPreview(MCPPublicModel):
    application_id: UUID
    proposal_id: UUID
    action: Literal["create", "update"]
    status: Literal["prepared"] = "prepared"
    routine_titles: list[str]
    source_routine_id: str | None = None
    confirmation_token: str
    warning: str


class RoutineApplicationResult(MCPPublicModel):
    application_id: UUID
    proposal_id: UUID
    action: Literal["create", "update"]
    status: Literal["applied", "failed", "uncertain", "partial"]
    routine_ids: list[str]
    error_code: str | None = None
    sync_status: Literal["not_configured", "not_run", "succeeded", "failed"] = "not_run"
    message: str


class RoutineApplicationCommand(MCPPublicModel):
    application_id: UUID
    proposal_id: UUID
    action: Literal["create", "update"]
    source_routine_id: str | None = None
    source_routine_hash: str | None = None
    plan: TrainingPlanProposalInput


class RoutineApplicationReconciliationContext(MCPPublicModel):
    application_id: UUID
    proposal_id: UUID
    action: Literal["create", "update"]
    status: Literal["uncertain", "partial"]
    applied_at: datetime
    recorded_routine_ids: list[str]
    plan: TrainingPlanProposalInput


class RoutineApplicationReconciliationResult(MCPPublicModel):
    application_id: UUID
    proposal_id: UUID
    status: Literal["applied", "partial", "uncertain"]
    matched_workout_indexes: list[int]
    routine_ids: list[str]
    error_code: str | None = None
    sync_status: Literal["not_configured", "not_run", "succeeded", "failed"] = "not_run"
    message: str


class WorkoutReviewAcknowledgement(MCPPublicModel):
    review_id: UUID
    workout_external_id: str
    status: Literal["completed"] = "completed"
