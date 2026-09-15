from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from gym_coach.coaching.assessment import calculate_mifflin_st_jeor
from gym_coach.integrations.health_connect.service import HealthBatch
from gym_coach.mcp.schemas import AthleteMeasurementView
from gym_coach.tracking.activity import ActivityDay, assess_recovery
from gym_coach.tracking.body import BodyMeasurementObservation, body_measurement_trends
from gym_coach.tracking.calculations import calculate_target, difference, measurement_trends
from gym_coach.tracking.schemas import TargetParameters


def test_targets_conserve_energy_and_apply_explicit_adjustment() -> None:
    params = TargetParameters(
        effective_from=date.today(),
        activity_factor="1.5",
        energy_adjustment_percent=-10,
        protein_g_per_kg="1.6",
        fat_energy_percent=30,
        rationale="Moderate activity and confirmed gradual fat loss goal",
    )
    maintenance, target = calculate_target(1800, Decimal(80), params)
    assert maintenance == 2700
    assert target.energy_kcal == 2430
    assert target.protein_g == 128
    assert target.fat_g == 81
    assert target.carbohydrate_g == Decimal("297.25")
    assert target.fiber_g == Decimal("34.02")
    assert target.protein_g * 4 + target.carbohydrate_g * 4 + target.fat_g * 9 == target.energy_kcal


def test_nutrition_difference_preserves_unknown_fiber() -> None:
    from gym_coach.nutrition.schemas import Nutrients

    target = Nutrients(
        energy_kcal=2000,
        protein_g=150,
        carbohydrate_g=200,
        fat_g=70,
        fiber_g=28,
    )
    intake = target.model_copy(update={"fiber_g": None})
    result = difference(intake, target)
    assert result.energy_kcal == 0
    assert result.fiber_g is None


@pytest.mark.parametrize("age", [-1, 0, 15, 101])
def test_energy_equation_does_not_coerce_age(age: int) -> None:
    assert (
        calculate_mifflin_st_jeor(
            weight_kg=Decimal(80), height_cm=Decimal(180), age=age, sex="male"
        )
        is None
    )


def test_trends_require_repeated_weight_and_keep_missing_metrics_separate() -> None:
    end = date.today()
    rows = [
        AthleteMeasurementView(
            measurement_id=uuid4(),
            measured_on=end - timedelta(days=d),
            weight_kg=Decimal(80 if d >= 7 else 79),
        )
        for d in (0, 1, 2, 7, 8, 9)
    ]
    rows.append(
        AthleteMeasurementView(measurement_id=uuid4(), measured_on=end, waist_cm=Decimal(90))
    )
    trends = measurement_trends(rows, end)
    assert trends[0].change == -1
    assert trends[1].recent_mean == 90
    assert trends[1].change is None
    assert measurement_trends(rows[:2], end)[0].change is None


def test_health_batch_rejects_duplicate_dates_and_preserves_unknowns() -> None:
    sample = ActivityDay(day=date.today(), timezone="UTC", observed_at=datetime.now(UTC))
    assert sample.steps is None
    with pytest.raises(ValidationError, match="Duplicate"):
        HealthBatch(request_id=uuid4(), consent_confirmed=True, days=[sample, sample])
    with pytest.raises(ValidationError, match="timezone"):
        ActivityDay(day=date.today(), timezone="not-a-zone", observed_at=datetime.now(UTC))


def test_recovery_compares_recent_data_with_the_personal_baseline() -> None:
    end = date(2026, 9, 14)
    observed_at = datetime(2026, 9, 15, tzinfo=UTC)
    days = [
        ActivityDay(
            day=end - timedelta(days=offset),
            timezone="UTC",
            sleep_asleep_minutes=Decimal(360 if offset < 7 else 450),
            resting_heart_rate_bpm=Decimal(66 if offset < 7 else 60),
            hrv_rmssd_ms=Decimal(36 if offset < 7 else 50),
            steps=8000,
            observed_at=observed_at,
        )
        for offset in range(28)
    ]
    recovery = assess_recovery(days, end)
    assert recovery.status == "possible_strain"
    assert recovery.adverse_signal_count == 3
    assert [trend.signal for trend in recovery.trends] == [
        "adverse",
        "adverse",
        "adverse",
        "stable",
    ]


def test_recovery_does_not_replace_missing_data_with_zeroes() -> None:
    recovery = assess_recovery(
        [ActivityDay(day=date.today(), timezone="UTC", observed_at=datetime.now(UTC))],
        date.today(),
    )
    assert recovery.status == "insufficient"
    assert all(trend.signal == "insufficient" for trend in recovery.trends)


def test_wearable_trends_use_one_morning_measurement_per_day() -> None:
    end = date.today()
    observed_at = datetime.now(UTC)
    rows = [
        BodyMeasurementObservation(
            external_id=uuid4(),
            measured_at=datetime.combine(end - timedelta(days=day_offset), datetime.min.time(), UTC)
            + timedelta(hours=7, minutes=reading_offset),
            measured_on=end - timedelta(days=day_offset),
            timezone="UTC",
            weight_kg=weight,
            body_fat_percent=Decimal(18),
            body_fat_method="consumer_bia",
            observed_at=observed_at,
        )
        for day_offset, reading_offset, weight in (
            (0, 0, Decimal(79)),
            (0, 30, Decimal(90)),
            (1, 0, Decimal(79)),
            (2, 0, Decimal(79)),
            (7, 0, Decimal(80)),
            (8, 0, Decimal(80)),
            (9, 0, Decimal(80)),
        )
    ]
    trends = body_measurement_trends(rows, end)
    assert trends[0].recent_count == 3
    assert trends[0].change == -1


def test_prescription_comparison_distinguishes_missing_unknown_and_below() -> None:
    from gym_coach.mcp.schemas import CompletedSet, PlannedSet
    from gym_coach.tracking.training import compare_set

    planned = PlannedSet(position=1, rep_range_start=8, rep_range_end=12, weight_kg="50")
    assert compare_set(planned, None).status == "missing"
    assert compare_set(planned, CompletedSet(position=1, reps=7)).status == "below"
    assert compare_set(planned, CompletedSet(position=1)).status == "unknown"
    met = compare_set(planned, CompletedSet(position=1, reps=10, weight_kg="55"))
    assert met.status == "met" and met.load_difference_kg == 5
    assert (
        compare_set(
            PlannedSet(position=1, duration_seconds=60), CompletedSet(position=1, reps=60)
        ).status
        == "unknown"
    )


def test_comparison_keeps_repeated_exercises_and_marks_extra_work() -> None:
    from gym_coach.mcp.schemas import (
        CompletedExercise,
        CompletedSet,
        PlannedExercise,
        PlannedSet,
        TrainingRoutine,
        TrainingWorkout,
    )
    from gym_coach.tracking.training import compare_workout

    routine = TrainingRoutine(
        external_id="r",
        title="Routine",
        exercises=[
            PlannedExercise(
                position=i,
                exercise_template_external_id="e",
                title="Repeated",
                sets=[PlannedSet(position=1, reps=8)],
            )
            for i in (1, 2)
        ],
    )
    workout = TrainingWorkout(
        external_id="w",
        title="Workout",
        routine_external_id="r",
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC),
        exercises=[
            CompletedExercise(
                position=1,
                exercise_template_external_id="e",
                title="Repeated",
                sets=[CompletedSet(position=1, reps=8)],
            )
        ],
    )
    result = compare_workout(routine, workout)
    assert result.met_sets == 1 and result.missing_sets == 1
    assert [e.occurrence for e in result.exercises] == [1, 2]
    assert any("Historical" in limit for limit in result.limitations)
