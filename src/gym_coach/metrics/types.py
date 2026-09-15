from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SetSample:
    position: int
    set_type: str | None
    weight_kg: Decimal | None
    reps: int | None
    distance_meters: Decimal | None = None
    duration_seconds: int | None = None
    rpe: float | None = None


@dataclass(frozen=True, slots=True)
class ExercisePerformance:
    workout_external_id: str
    exercise_template_external_id: str
    exercise_type: str
    performed_at: datetime
    sets: tuple[SetSample, ...]


@dataclass(frozen=True, slots=True)
class WorkoutOccurrence:
    external_id: str
    performed_at: datetime
    routine_external_id: str | None


@dataclass(frozen=True, slots=True)
class SessionMetric:
    workout_external_id: str
    performed_at: datetime
    total_reps: int
    volume_kg_reps: Decimal
    best_e1rm_kg: Decimal | None
    qualifying_sets: int
    working_sets: int
    best_weight_kg: Decimal | None
    minimum_weight_kg: Decimal | None
    max_reps: int | None
    total_distance_meters: Decimal
    total_duration_seconds: int
    mean_rpe: Decimal | None


@dataclass(frozen=True, slots=True)
class ExerciseProgress:
    exercise_template_external_id: str
    sessions: tuple[SessionMetric, ...]
    latest_e1rm_kg: Decimal | None
    previous_e1rm_kg: Decimal | None
    e1rm_change_kg: Decimal | None
    e1rm_change_percent: Decimal | None
    progress_metric: str = "e1rm_kg"
    latest_metric_value: Decimal | None = None
    previous_metric_value: Decimal | None = None
    best_metric_value: Decimal | None = None
    metric_change_percent: Decimal | None = None
    latest_is_personal_record: bool = False


@dataclass(frozen=True, slots=True)
class AdherenceMetric:
    window_days: int
    target_sessions_per_week: Decimal
    expected_sessions: Decimal
    completed_sessions: int
    adherence_percent: Decimal
    matched_routine_sessions: int


@dataclass(frozen=True, slots=True)
class StagnationRule:
    minimum_sessions: int = 4
    lookback_sessions: int = 6
    minimum_span_days: int = 14
    minimum_improvement_percent: Decimal = Decimal("2.0")


DEFAULT_STAGNATION_RULE = StagnationRule()


@dataclass(frozen=True, slots=True)
class StagnationResult:
    exercise_template_external_id: str
    is_stalled: bool
    reason: str
    qualifying_sessions: int
    span_days: int
    improvement_percent: Decimal | None


@dataclass(frozen=True, slots=True)
class MetricsSummary:
    workouts: int
    total_reps: int
    total_volume_kg_reps: Decimal
    adherence: AdherenceMetric
    stalled_exercises: tuple[StagnationResult, ...]
