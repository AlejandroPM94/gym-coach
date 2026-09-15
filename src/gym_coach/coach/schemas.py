from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AthleteProfileInput(StrictModel):
    experience_level: Literal["beginner", "intermediate", "advanced"] | None = None
    birth_year: Annotated[int | None, Field(ge=1900, le=2100)] = None
    sex_for_energy_equation: Literal["female", "male", "unspecified"] = "unspecified"
    height_cm: Annotated[Decimal | None, Field(ge=100, le=250)] = None
    training_days_per_week: Annotated[int, Field(ge=1, le=7)]
    session_duration_minutes: Annotated[int | None, Field(ge=15, le=300)] = None
    equipment: list[str] = Field(default_factory=list, max_length=50)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    preferences: list[str] = Field(default_factory=list, max_length=30)
    limitations_reviewed: bool = False
    preferences_reviewed: bool = False
    occupation_activity: Literal["sedentary", "light", "moderate", "high"] | None = None
    average_daily_steps: Annotated[int | None, Field(ge=0, le=100_000)] = None
    sleep_hours: Annotated[float | None, Field(ge=0, le=24)] = None
    sleep_quality: Annotated[int | None, Field(ge=1, le=5)] = None
    stress_level: Annotated[int | None, Field(ge=1, le=5)] = None
    dietary_pattern: Annotated[str | None, Field(max_length=64)] = None
    dietary_restrictions: list[str] = Field(default_factory=list, max_length=30)
    food_allergies: list[str] = Field(default_factory=list, max_length=30)
    nutrition_preferences: list[str] = Field(default_factory=list, max_length=30)
    nutrition_tracking_preference: Literal["none", "habits", "portions", "calories"] | None = None
    health_conditions: list[str] = Field(default_factory=list, max_length=30)
    medications_affecting_training: list[str] = Field(default_factory=list, max_length=30)
    lifestyle_reviewed: bool = False
    nutrition_reviewed: bool = False
    health_reviewed: bool = False

    @field_validator("birth_year")
    @classmethod
    def birth_year_not_future(cls, value: int | None) -> int | None:
        if value is not None and value > date.today().year:
            raise ValueError("Birth year cannot be in the future")
        return value


class AthleteProfileView(AthleteProfileInput):
    id: UUID
    version: int = 1


class TrainingGoalInput(StrictModel):
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


class TrainingGoalView(TrainingGoalInput):
    id: UUID
    version: int
    status: Literal["active", "completed", "archived"]


class EvidenceFact(StrictModel):
    id: Annotated[str, Field(pattern=r"^[a-z0-9_.:-]+$")]
    category: Literal["profile", "goal", "routine", "metric", "history"]
    description: str
    value: str
    unit: str | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None


class RoutineSetContext(StrictModel):
    set_type: str | None
    weight_kg: str | None
    reps: int | None
    rep_range_start: int | None
    rep_range_end: int | None


class RoutineExerciseContext(StrictModel):
    exercise_template_id: str
    title: str
    rest_seconds: int | None
    sets: list[RoutineSetContext]


class RoutineContext(StrictModel):
    routine_id: str
    title: str
    exercises: list[RoutineExerciseContext]


class CoachContext(StrictModel):
    profile: AthleteProfileView
    goals: list[TrainingGoalView]
    routines: list[RoutineContext]
    evidence: list[EvidenceFact]


class CoachFinding(StrictModel):
    statement: Annotated[str, Field(min_length=1, max_length=1000)]
    evidence_ids: Annotated[list[str], Field(min_length=1)]


class ProposedSet(StrictModel):
    set_type: Literal["warmup", "normal", "drop", "failure"] = "normal"
    weight_kg: Annotated[Decimal | None, Field(ge=0, le=500)] = None
    reps_min: Annotated[int | None, Field(ge=1, le=100)] = None
    reps_max: Annotated[int | None, Field(ge=1, le=100)] = None
    duration_seconds_min: Annotated[int | None, Field(ge=1, le=7200)] = None
    duration_seconds_max: Annotated[int | None, Field(ge=1, le=7200)] = None
    distance_meters_min: Annotated[Decimal | None, Field(gt=0, le=100_000)] = None
    distance_meters_max: Annotated[Decimal | None, Field(gt=0, le=100_000)] = None
    target_rpe: Annotated[float | None, Field(ge=1, le=10)] = None
    load_guidance: Annotated[str | None, Field(max_length=300)] = None

    @model_validator(mode="after")
    def validate_range(self) -> "ProposedSet":
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


class ProposedExercise(StrictModel):
    exercise_template_id: str | None = None
    title: str
    rest_seconds: Annotated[int, Field(ge=0, le=900)]
    sets: Annotated[list[ProposedSet], Field(min_length=1, max_length=20)]
    notes: str | None = None
    superset_group: Annotated[
        str | None, Field(default=None, min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.:-]+$")
    ] = None


class ProposedWorkout(StrictModel):
    title: str
    exercises: Annotated[list[ProposedExercise], Field(min_length=1, max_length=30)]
    optional: bool = False
    location: Literal["gym", "home", "outdoors", "other"] = "gym"
    estimated_duration_minutes: Annotated[int | None, Field(ge=5, le=300)] = None

    @model_validator(mode="after")
    def validate_superset_groups(self) -> "ProposedWorkout":
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


class PlanChangeJustification(StrictModel):
    description: Annotated[str, Field(min_length=1, max_length=2000)]
    evidence_ids: Annotated[list[str], Field(min_length=1, max_length=30)]


class CoachProposalOutput(StrictModel):
    kind: Literal["new_routine", "routine_update", "progression"]
    title: str
    summary: str
    rationale: str
    evidence_ids: Annotated[list[str], Field(min_length=1)]
    source_routine_id: str | None = None
    workouts: Annotated[list[ProposedWorkout], Field(min_length=1, max_length=7)]
    changes: list[PlanChangeJustification] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_change_evidence(self) -> "CoachProposalOutput":
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


class CoachResponse(StrictModel):
    answer: Annotated[str, Field(min_length=1, max_length=4000)]
    evidence_ids: Annotated[list[str], Field(min_length=1)]
    findings: list[CoachFinding] = Field(default_factory=list)
    proposal: CoachProposalOutput | None = None


class StoredProposalView(StrictModel):
    id: UUID
    kind: str
    status: Literal["draft", "approved", "rejected"]
    title: str
    summary: str
    model_name: str
    created_at: datetime
    decided_at: datetime | None
