from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from gym_coach.metrics.calculations import (
    calculate_adherence,
    calculate_exercise_progress,
    calculate_session_metric,
    calculate_summary,
    detect_stagnation,
    estimate_epley_1rm,
    set_volume,
)
from gym_coach.metrics.types import (
    ExercisePerformance,
    SetSample,
    StagnationRule,
    WorkoutOccurrence,
)

NOW = datetime(2026, 8, 5, 12, tzinfo=UTC)


def _set(
    weight: str | None,
    reps: int | None,
    *,
    set_type: str | None = "normal",
    distance_meters: str | None = None,
    duration_seconds: int | None = None,
    rpe: float | None = None,
) -> SetSample:
    return SetSample(
        position=0,
        set_type=set_type,
        weight_kg=Decimal(weight) if weight is not None else None,
        reps=reps,
        distance_meters=Decimal(distance_meters) if distance_meters is not None else None,
        duration_seconds=duration_seconds,
        rpe=rpe,
    )


def _performance(
    template_id: str,
    days_ago: int,
    weight: str,
    reps: int,
    *,
    exercise_type: str = "weight_reps",
) -> ExercisePerformance:
    return ExercisePerformance(
        workout_external_id=f"workout-{template_id}-{days_ago}",
        exercise_template_external_id=template_id,
        exercise_type=exercise_type,
        performed_at=NOW - timedelta(days=days_ago),
        sets=(_set(weight, reps),),
    )


@pytest.mark.parametrize(
    ("weight", "reps", "expected"),
    [
        (Decimal("100"), 1, Decimal("103.33")),
        (Decimal("100"), 10, Decimal("133.33")),
        (Decimal("82.5"), 8, Decimal("104.50")),
        (None, 8, None),
        (Decimal("0"), 8, None),
        (Decimal("100"), 0, None),
        (Decimal("100"), 13, None),
    ],
)
def test_epley_estimate_has_explicit_domain(
    weight: Decimal | None, reps: int, expected: Decimal | None
) -> None:
    assert estimate_epley_1rm(weight, reps) == expected


def test_volume_only_applies_to_normal_weight_reps_sets() -> None:
    assert set_volume(_set("50", 8), "weight_reps") == Decimal("400.00")
    assert set_volume(_set("50", 8), "bodyweight_weighted") is None
    assert set_volume(_set("50", 8, set_type="warmup"), "weight_reps") is None
    assert set_volume(_set(None, 8), "weight_reps") is None


def test_session_metric_separates_reps_volume_and_e1rm() -> None:
    performance = ExercisePerformance(
        workout_external_id="workout-1",
        exercise_template_external_id="template-1",
        exercise_type="weight_reps",
        performed_at=NOW,
        sets=(_set("50", 8), _set("55", 5), _set("20", 20), _set("20", 5, set_type="warmup")),
    )
    metric = calculate_session_metric(performance)
    assert metric.total_reps == 33
    assert metric.volume_kg_reps == Decimal("1075.00")
    assert metric.best_e1rm_kg == Decimal("64.17")
    assert metric.qualifying_sets == 3


def test_session_metric_preserves_effort_distance_and_duration() -> None:
    performance = ExercisePerformance(
        workout_external_id="workout-1",
        exercise_template_external_id="template-1",
        exercise_type="distance_duration",
        performed_at=NOW,
        sets=(
            _set(None, None, distance_meters="500", duration_seconds=120, rpe=7),
            _set(None, None, distance_meters="750", duration_seconds=180, rpe=8),
        ),
    )
    metric = calculate_session_metric(performance)
    assert metric.working_sets == 2
    assert metric.total_distance_meters == Decimal("1250.00")
    assert metric.total_duration_seconds == 300
    assert metric.mean_rpe == Decimal("7.50")


def test_progress_uses_the_exercise_modality_and_needs_history_for_a_record() -> None:
    repetitions = tuple(
        ExercisePerformance(
            f"workout-{index}",
            "repetitions",
            "reps_only",
            NOW - timedelta(days=days),
            (_set(None, reps),),
        )
        for index, (days, reps) in enumerate(((14, 10), (7, 12), (0, 15)))
    )
    progress = calculate_exercise_progress("repetitions", repetitions)
    assert progress.progress_metric == "repetitions"
    assert progress.latest_metric_value == 15
    assert progress.metric_change_percent == Decimal("25.00")
    assert progress.latest_is_personal_record is True

    first = calculate_exercise_progress("repetitions", repetitions[:1])
    assert first.latest_is_personal_record is False

    missing_latest = (
        *repetitions,
        ExercisePerformance(
            "workout-missing",
            "repetitions",
            "reps_only",
            NOW + timedelta(days=1),
            (_set(None, None),),
        ),
    )
    assert (
        calculate_exercise_progress("repetitions", missing_latest).latest_is_personal_record
        is False
    )


def test_assisted_bodyweight_treats_less_assistance_as_progress() -> None:
    performances = tuple(
        _performance("assisted", days, weight, 8, exercise_type="bodyweight_assisted")
        for days, weight in ((28, "30"), (21, "28"), (14, "26"), (7, "24"), (0, "20"))
    )
    progress = calculate_exercise_progress("assisted", performances)
    stalled = detect_stagnation(
        "assisted", progress.sessions, progress_metric=progress.progress_metric
    )
    assert progress.progress_metric == "assistance_kg"
    assert progress.best_metric_value == 20
    assert progress.latest_is_personal_record is True
    assert stalled.is_stalled is False
    assert stalled.improvement_percent == Decimal("33.33")


def test_duration_stagnation_is_not_inferred_without_a_pace_or_load_context() -> None:
    performance = ExercisePerformance(
        "workout",
        "duration",
        "duration",
        NOW,
        (_set(None, None, duration_seconds=60),),
    )
    progress = calculate_exercise_progress("duration", (performance,))
    result = detect_stagnation(
        "duration", progress.sessions, progress_metric=progress.progress_metric
    )
    assert result.reason == "unsupported_progress_metric"


def test_progress_never_mixes_exercise_templates() -> None:
    performances = (
        _performance("target", 14, "80", 5),
        _performance("other", 7, "200", 5),
        _performance("target", 0, "85", 5),
    )
    progress = calculate_exercise_progress("target", performances)
    assert len(progress.sessions) == 2
    assert progress.previous_e1rm_kg == Decimal("93.33")
    assert progress.latest_e1rm_kg == Decimal("99.17")
    assert progress.e1rm_change_kg == Decimal("5.84")
    assert progress.e1rm_change_percent == Decimal("6.26")


def test_adherence_is_capped_and_tracks_routine_matches() -> None:
    workouts = tuple(
        WorkoutOccurrence(
            external_id=f"workout-{index}",
            performed_at=NOW - timedelta(days=index),
            routine_external_id="routine-1" if index % 2 == 0 else None,
        )
        for index in range(5)
    )
    adherence = calculate_adherence(
        workouts,
        as_of=NOW,
        window_days=7,
        target_sessions_per_week=Decimal("4"),
    )
    assert adherence.expected_sessions == Decimal("4.00")
    assert adherence.completed_sessions == 5
    assert adherence.adherence_percent == Decimal("100.00")
    assert adherence.matched_routine_sessions == 3


@pytest.mark.parametrize(("days", "target"), [(0, Decimal("4")), (7, Decimal("0"))])
def test_adherence_rejects_invalid_configuration(days: int, target: Decimal) -> None:
    with pytest.raises(ValueError):
        calculate_adherence((), as_of=NOW, window_days=days, target_sessions_per_week=target)


def test_stagnation_requires_sessions_and_time() -> None:
    two = tuple(calculate_session_metric(_performance("target", days, "100", 5)) for days in (7, 0))
    assert detect_stagnation("target", two).reason == "insufficient_sessions"
    four_close = tuple(
        calculate_session_metric(_performance("target", days, "100", 5)) for days in (3, 2, 1, 0)
    )
    assert detect_stagnation("target", four_close).reason == "insufficient_time_span"


def test_stagnation_and_progress_are_deterministic() -> None:
    stalled_sessions = tuple(
        calculate_session_metric(_performance("target", days, "100", 5))
        for days in (28, 21, 14, 7, 0)
    )
    stalled = detect_stagnation("target", stalled_sessions)
    assert stalled.is_stalled is True
    assert stalled.improvement_percent == Decimal("0.00")

    progressing_sessions = tuple(
        calculate_session_metric(_performance("target", days, weight, 5))
        for days, weight in ((28, "100"), (21, "101"), (14, "102"), (7, "103"), (0, "104"))
    )
    progressing = detect_stagnation("target", progressing_sessions)
    assert progressing.is_stalled is False
    assert progressing.reason == "progressing"
    assert progressing.improvement_percent == Decimal("3.99")


def test_summary_excludes_non_strength_volume_and_old_workouts() -> None:
    workouts = (
        WorkoutOccurrence("recent", NOW - timedelta(days=1), "routine-1"),
        WorkoutOccurrence("old", NOW - timedelta(days=40), "routine-1"),
    )
    performances = (
        ExercisePerformance("recent", "strength", "weight_reps", NOW, (_set("50", 8),)),
        ExercisePerformance("recent", "timed", "duration", NOW, (_set("50", 8),)),
        ExercisePerformance("old", "strength", "weight_reps", NOW, (_set("100", 10),)),
    )
    summary = calculate_summary(
        workouts,
        performances,
        as_of=NOW,
        window_days=28,
        target_sessions_per_week=Decimal("3"),
        stagnation_rule=StagnationRule(minimum_sessions=2, lookback_sessions=2),
    )
    assert summary.workouts == 1
    assert summary.total_reps == 16
    assert summary.total_volume_kg_reps == Decimal("400.00")
