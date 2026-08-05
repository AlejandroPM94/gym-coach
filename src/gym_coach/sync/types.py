from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class NormalizedSet:
    position: int
    set_type: str | None
    weight_kg: Decimal | None
    reps: int | None
    distance_meters: Decimal | None
    duration_seconds: int | None
    rpe: float | None
    custom_metric: Decimal | None
    rep_range_start: int | None = None
    rep_range_end: int | None = None


@dataclass(frozen=True, slots=True)
class NormalizedExercise:
    position: int
    title: str
    notes: str | None
    exercise_template_external_id: str
    superset_id: int | None
    rest_seconds: int | None
    sets: tuple[NormalizedSet, ...]


@dataclass(frozen=True, slots=True)
class UserRecord:
    external_id: str
    name: str | None
    profile_url: str | None
    content_hash: str


@dataclass(frozen=True, slots=True)
class ExerciseTemplateRecord:
    external_id: str
    title: str
    exercise_type: str
    primary_muscle_group: str
    secondary_muscle_groups: tuple[str, ...]
    equipment: str | None
    is_custom: bool | None
    content_hash: str


@dataclass(frozen=True, slots=True)
class RoutineRecord:
    external_id: str
    title: str
    folder_id: int | None
    source_created_at: datetime | None
    source_updated_at: datetime | None
    exercises: tuple[NormalizedExercise, ...]
    content_hash: str


@dataclass(frozen=True, slots=True)
class WorkoutRecord:
    external_id: str
    title: str
    description: str | None
    routine_external_id: str | None
    start_time: datetime
    end_time: datetime
    source_created_at: datetime | None
    source_updated_at: datetime | None
    exercises: tuple[NormalizedExercise, ...]
    content_hash: str


@dataclass(frozen=True, slots=True)
class HevySnapshot:
    user: UserRecord
    exercise_templates: tuple[ExerciseTemplateRecord, ...]
    routines: tuple[RoutineRecord, ...]
    workouts: tuple[WorkoutRecord, ...]
    completed_at: datetime


@dataclass(slots=True)
class SyncCounts:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0

    def add(self, outcome: str) -> None:
        if outcome == "inserted":
            self.inserted += 1
        elif outcome == "updated":
            self.updated += 1
        else:
            self.unchanged += 1


@dataclass(frozen=True, slots=True)
class SyncResult:
    run_id: str
    counts: SyncCounts = field(default_factory=SyncCounts)
