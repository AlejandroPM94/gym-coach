from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from gym_coach.metrics.types import (
    DEFAULT_STAGNATION_RULE,
    AdherenceMetric,
    ExercisePerformance,
    ExerciseProgress,
    MetricsSummary,
    SessionMetric,
    SetSample,
    StagnationResult,
    StagnationRule,
    WorkoutOccurrence,
)

STRENGTH_EXERCISE_TYPE = "weight_reps"
WORKING_SET_TYPE = "normal"
MAX_E1RM_REPS = 12
TWO_PLACES = Decimal("0.01")


def estimate_epley_1rm(weight_kg: Decimal | None, reps: int | None) -> Decimal | None:
    """Estimate 1RM with Epley for positive loads and 1-12 repetitions."""
    if weight_kg is None or reps is None or weight_kg <= 0 or reps < 1 or reps > MAX_E1RM_REPS:
        return None
    estimate = weight_kg * (Decimal(1) + Decimal(reps) / Decimal(30))
    return _round(estimate)


def set_volume(set_sample: SetSample, exercise_type: str) -> Decimal | None:
    if (
        exercise_type != STRENGTH_EXERCISE_TYPE
        or set_sample.set_type != WORKING_SET_TYPE
        or set_sample.weight_kg is None
        or set_sample.reps is None
        or set_sample.weight_kg <= 0
        or set_sample.reps <= 0
    ):
        return None
    return _round(set_sample.weight_kg * set_sample.reps)


def calculate_session_metric(performance: ExercisePerformance) -> SessionMetric:
    working_sets = tuple(item for item in performance.sets if item.set_type == WORKING_SET_TYPE)
    volumes = [
        volume
        for item in working_sets
        if (volume := set_volume(item, performance.exercise_type)) is not None
    ]
    estimates = [
        estimate
        for item in working_sets
        if performance.exercise_type == STRENGTH_EXERCISE_TYPE
        and (estimate := estimate_epley_1rm(item.weight_kg, item.reps)) is not None
    ]
    weights = [item.weight_kg for item in working_sets if item.weight_kg is not None]
    repetitions = [item.reps for item in working_sets if item.reps is not None]
    rpes = [Decimal(str(item.rpe)) for item in working_sets if item.rpe is not None]
    return SessionMetric(
        workout_external_id=performance.workout_external_id,
        performed_at=performance.performed_at,
        total_reps=sum(
            item.reps for item in working_sets if item.reps is not None and item.reps > 0
        ),
        volume_kg_reps=_round(sum(volumes, start=Decimal(0))),
        best_e1rm_kg=max(estimates, default=None),
        qualifying_sets=len(volumes),
        working_sets=len(working_sets),
        best_weight_kg=max(weights, default=None),
        minimum_weight_kg=min(weights, default=None),
        max_reps=max(repetitions, default=None),
        total_distance_meters=_round(
            sum(
                (item.distance_meters for item in working_sets if item.distance_meters is not None),
                start=Decimal(0),
            )
        ),
        total_duration_seconds=sum(
            item.duration_seconds
            for item in working_sets
            if item.duration_seconds is not None and item.duration_seconds > 0
        ),
        mean_rpe=_round(sum(rpes, Decimal(0)) / len(rpes)) if rpes else None,
    )


def calculate_exercise_progress(
    exercise_template_external_id: str,
    performances: tuple[ExercisePerformance, ...],
) -> ExerciseProgress:
    relevant = sorted(
        (
            item
            for item in performances
            if item.exercise_template_external_id == exercise_template_external_id
        ),
        key=lambda item: item.performed_at,
    )
    sessions = tuple(calculate_session_metric(item) for item in relevant)
    e1rm_sessions = tuple(item for item in sessions if item.best_e1rm_kg is not None)
    latest = e1rm_sessions[-1].best_e1rm_kg if e1rm_sessions else None
    previous = e1rm_sessions[-2].best_e1rm_kg if len(e1rm_sessions) >= 2 else None
    change = _round(latest - previous) if latest is not None and previous is not None else None
    change_percent = (
        _round(change / previous * 100)
        if change is not None and previous is not None and previous > 0
        else None
    )
    exercise_type = relevant[-1].exercise_type if relevant else "unknown"
    metric, values, lower_is_better = _progress_values(exercise_type, sessions)
    latest_metric = values[-1] if values else None
    previous_metric = values[-2] if len(values) >= 2 else None
    best_metric = (min(values) if lower_is_better else max(values)) if values else None
    metric_change = _metric_change(latest_metric, previous_metric, lower_is_better)
    previous_values = values[:-1]
    latest_session_value = (
        _session_progress_value(exercise_type, sessions[-1]) if sessions else None
    )
    latest_is_record = bool(
        latest_metric is not None
        and latest_session_value is not None
        and latest_metric == latest_session_value
        and previous_values
        and (
            latest_metric < min(previous_values)
            if lower_is_better
            else latest_metric > max(previous_values)
        )
    )
    return ExerciseProgress(
        exercise_template_external_id=exercise_template_external_id,
        sessions=sessions,
        latest_e1rm_kg=latest,
        previous_e1rm_kg=previous,
        e1rm_change_kg=change,
        e1rm_change_percent=change_percent,
        progress_metric=metric,
        latest_metric_value=latest_metric,
        previous_metric_value=previous_metric,
        best_metric_value=best_metric,
        metric_change_percent=metric_change,
        latest_is_personal_record=latest_is_record,
    )


def _progress_values(
    exercise_type: str, sessions: tuple[SessionMetric, ...]
) -> tuple[str, list[Decimal], bool]:
    if exercise_type == "weight_reps":
        return "e1rm_kg", [s.best_e1rm_kg for s in sessions if s.best_e1rm_kg is not None], False
    if exercise_type == "bodyweight_weighted":
        return (
            "external_load_kg",
            [s.best_weight_kg for s in sessions if s.best_weight_kg is not None],
            False,
        )
    if exercise_type == "bodyweight_assisted":
        return (
            "assistance_kg",
            [s.minimum_weight_kg for s in sessions if s.minimum_weight_kg is not None],
            True,
        )
    if exercise_type in {"reps_only", "steps_duration"}:
        return (
            "repetitions",
            [Decimal(s.max_reps) for s in sessions if s.max_reps is not None],
            False,
        )
    if exercise_type in {"distance_duration", "short_distance_weight"}:
        return (
            "distance_meters",
            [s.total_distance_meters for s in sessions if s.total_distance_meters > 0],
            False,
        )
    if exercise_type in {"duration", "floors_duration"}:
        return (
            "duration_seconds",
            [Decimal(s.total_duration_seconds) for s in sessions if s.total_duration_seconds > 0],
            False,
        )
    return "unavailable", [], False


def _session_progress_value(exercise_type: str, session: SessionMetric) -> Decimal | None:
    if exercise_type == "weight_reps":
        return session.best_e1rm_kg
    if exercise_type == "bodyweight_weighted":
        return session.best_weight_kg
    if exercise_type == "bodyweight_assisted":
        return session.minimum_weight_kg
    if exercise_type in {"reps_only", "steps_duration"}:
        return Decimal(session.max_reps) if session.max_reps is not None else None
    if exercise_type in {"distance_duration", "short_distance_weight"}:
        return session.total_distance_meters if session.total_distance_meters > 0 else None
    if exercise_type in {"duration", "floors_duration"}:
        return (
            Decimal(session.total_duration_seconds) if session.total_duration_seconds > 0 else None
        )
    return None


def _metric_change(
    latest: Decimal | None, previous: Decimal | None, lower_is_better: bool
) -> Decimal | None:
    if latest is None or previous is None or previous == 0:
        return None
    change = previous - latest if lower_is_better else latest - previous
    return _round(change / abs(previous) * 100)


def calculate_adherence(
    workouts: tuple[WorkoutOccurrence, ...],
    *,
    as_of: datetime,
    window_days: int,
    target_sessions_per_week: Decimal,
) -> AdherenceMetric:
    if window_days < 1:
        raise ValueError("window_days must be at least 1")
    if target_sessions_per_week <= 0:
        raise ValueError("target_sessions_per_week must be positive")
    start = as_of - timedelta(days=window_days)
    completed = tuple(item for item in workouts if start < item.performed_at <= as_of)
    expected = _round(target_sessions_per_week * Decimal(window_days) / Decimal(7))
    raw_percent = Decimal(len(completed)) / expected * 100
    return AdherenceMetric(
        window_days=window_days,
        target_sessions_per_week=target_sessions_per_week,
        expected_sessions=expected,
        completed_sessions=len(completed),
        adherence_percent=_round(min(raw_percent, Decimal(100))),
        matched_routine_sessions=sum(item.routine_external_id is not None for item in completed),
    )


def detect_stagnation(
    exercise_template_external_id: str,
    sessions: tuple[SessionMetric, ...],
    rule: StagnationRule = DEFAULT_STAGNATION_RULE,
    *,
    progress_metric: str = "e1rm_kg",
) -> StagnationResult:
    _validate_stagnation_rule(rule)
    if progress_metric in {"duration_seconds", "unavailable"}:
        return StagnationResult(
            exercise_template_external_id, False, "unsupported_progress_metric", 0, 0, None
        )
    accessors: dict[str, Callable[[SessionMetric], Decimal | None]] = {
        "e1rm_kg": lambda item: item.best_e1rm_kg,
        "external_load_kg": lambda item: item.best_weight_kg,
        "assistance_kg": lambda item: item.minimum_weight_kg,
        "repetitions": lambda item: Decimal(item.max_reps) if item.max_reps is not None else None,
        "distance_meters": lambda item: (
            item.total_distance_meters if item.total_distance_meters > 0 else None
        ),
    }
    value_for = accessors.get(progress_metric, accessors["e1rm_kg"])
    eligible = tuple(item for item in sessions if value_for(item) is not None)
    recent = tuple(sorted(eligible, key=lambda item: item.performed_at)[-rule.lookback_sessions :])
    if len(recent) < rule.minimum_sessions:
        return StagnationResult(
            exercise_template_external_id,
            False,
            "insufficient_sessions",
            len(recent),
            0,
            None,
        )
    span_days = (recent[-1].performed_at.date() - recent[0].performed_at.date()).days
    if span_days < rule.minimum_span_days:
        return StagnationResult(
            exercise_template_external_id,
            False,
            "insufficient_time_span",
            len(recent),
            span_days,
            None,
        )
    first = value_for(recent[0])
    measured = [value for item in recent if (value := value_for(item)) is not None]
    best = min(measured) if progress_metric == "assistance_kg" else max(measured)
    if first is None or first <= 0:
        improvement = None
    else:
        delta = first - best if progress_metric == "assistance_kg" else best - first
        improvement = _round(delta / abs(first) * 100)
    stalled = improvement is not None and improvement < rule.minimum_improvement_percent
    return StagnationResult(
        exercise_template_external_id,
        stalled,
        "below_improvement_threshold" if stalled else "progressing",
        len(recent),
        span_days,
        improvement,
    )


def calculate_summary(
    workouts: tuple[WorkoutOccurrence, ...],
    performances: tuple[ExercisePerformance, ...],
    *,
    as_of: datetime,
    window_days: int,
    target_sessions_per_week: Decimal,
    stagnation_rule: StagnationRule = DEFAULT_STAGNATION_RULE,
) -> MetricsSummary:
    _validate_stagnation_rule(stagnation_rule)
    start = as_of - timedelta(days=window_days)
    recent_workout_ids = {
        item.external_id for item in workouts if start < item.performed_at <= as_of
    }
    recent_performances = tuple(
        item for item in performances if item.workout_external_id in recent_workout_ids
    )
    session_metrics = tuple(calculate_session_metric(item) for item in recent_performances)
    grouped: dict[str, list[SessionMetric]] = defaultdict(list)
    for performance, metric in zip(recent_performances, session_metrics, strict=True):
        grouped[performance.exercise_template_external_id].append(metric)
    stalled_results = []
    for template_id, items in sorted(grouped.items()):
        progress = calculate_exercise_progress(template_id, recent_performances)
        result = detect_stagnation(
            template_id,
            tuple(items),
            stagnation_rule,
            progress_metric=progress.progress_metric,
        )
        if result.is_stalled:
            stalled_results.append(result)
    stalled = tuple(stalled_results)
    return MetricsSummary(
        workouts=len(recent_workout_ids),
        total_reps=sum(item.total_reps for item in session_metrics),
        total_volume_kg_reps=_round(
            sum((item.volume_kg_reps for item in session_metrics), start=Decimal(0))
        ),
        adherence=calculate_adherence(
            workouts,
            as_of=as_of,
            window_days=window_days,
            target_sessions_per_week=target_sessions_per_week,
        ),
        stalled_exercises=stalled,
    )


def _round(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _validate_stagnation_rule(rule: StagnationRule) -> None:
    if rule.minimum_sessions < 2 or rule.lookback_sessions < rule.minimum_sessions:
        raise ValueError("stagnation session thresholds are inconsistent")
    if rule.minimum_span_days < 1 or rule.minimum_improvement_percent < 0:
        raise ValueError("stagnation thresholds must be non-negative")
