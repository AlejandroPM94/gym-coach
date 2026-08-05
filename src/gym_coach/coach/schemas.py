from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AthleteProfileInput(StrictModel):
    experience_level: Literal["beginner", "intermediate", "advanced"]
    training_days_per_week: Annotated[int, Field(ge=1, le=7)]
    session_duration_minutes: Annotated[int | None, Field(ge=15, le=300)] = None
    equipment: list[str] = Field(default_factory=list, max_length=50)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    preferences: list[str] = Field(default_factory=list, max_length=30)


class AthleteProfileView(AthleteProfileInput):
    id: UUID


class TrainingGoalInput(StrictModel):
    goal_type: Literal["strength", "hypertrophy", "endurance", "health", "skill", "other"]
    description: Annotated[str, Field(min_length=3, max_length=1000)]
    priority: Annotated[int, Field(ge=1, le=5)] = 1
    target_date: date | None = None


class TrainingGoalView(TrainingGoalInput):
    id: UUID
    version: int
    status: Literal["active", "completed", "archived"]


class EvidenceFact(StrictModel):
    id: Annotated[str, Field(pattern=r"^[a-z0-9_.:-]+$")]
    category: Literal["profile", "goal", "routine", "metric"]
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
    reps_min: Annotated[int, Field(ge=1, le=100)]
    reps_max: Annotated[int, Field(ge=1, le=100)]
    target_rpe: Annotated[float | None, Field(ge=1, le=10)] = None
    load_guidance: Annotated[str | None, Field(max_length=300)] = None

    @model_validator(mode="after")
    def validate_range(self) -> "ProposedSet":
        if self.reps_max < self.reps_min:
            raise ValueError("reps_max must be greater than or equal to reps_min")
        return self


class ProposedExercise(StrictModel):
    exercise_template_id: str | None = None
    title: str
    rest_seconds: Annotated[int, Field(ge=0, le=900)]
    sets: Annotated[list[ProposedSet], Field(min_length=1, max_length=20)]
    notes: str | None = None


class ProposedWorkout(StrictModel):
    title: str
    exercises: Annotated[list[ProposedExercise], Field(min_length=1, max_length=30)]


class CoachProposalOutput(StrictModel):
    kind: Literal["new_routine", "routine_update", "progression"]
    title: str
    summary: str
    rationale: str
    evidence_ids: Annotated[list[str], Field(min_length=1)]
    source_routine_id: str | None = None
    workouts: Annotated[list[ProposedWorkout], Field(min_length=1, max_length=7)]


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
