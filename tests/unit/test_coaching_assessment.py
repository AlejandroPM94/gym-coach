from datetime import UTC, date, datetime
from decimal import Decimal

from gym_coach.coaching.assessment import (
    COACHING_RULES,
    HistoryFacts,
    assess_training_history,
    calculate_bmi,
    calculate_mifflin_st_jeor,
    protein_range,
)


def test_history_assessment_uses_logs_and_exposes_limits() -> None:
    result = assess_training_history(
        HistoryFacts(
            period_start=datetime(2026, 1, 1, tzinfo=UTC),
            period_end=datetime(2026, 8, 1, tzinfo=UTC),
            workout_count=95,
            active_week_count=31,
            distinct_exercise_count=42,
        ),
        as_of=date(2026, 8, 6),
    )

    assert result.history_level == "established"
    assert result.confidence == "high"
    assert result.workouts_per_active_week == "3.06"
    assert "technique" in result.limitations[0].lower()


def test_anthropometric_calculations_are_deterministic() -> None:
    assert calculate_bmi(Decimal("80"), Decimal("180")) == Decimal("24.7")
    assert (
        calculate_mifflin_st_jeor(
            weight_kg=Decimal("80"), height_cm=Decimal("180"), age=30, sex="male"
        )
        == 1780
    )
    assert (
        calculate_mifflin_st_jeor(
            weight_kg=Decimal("80"), height_cm=Decimal("180"), age=30, sex="unspecified"
        )
        is None
    )
    assert protein_range(Decimal("80")) == (112, 160)


def test_curated_rules_are_traceable_and_cover_fat_loss() -> None:
    assert {rule.topic for rule in COACHING_RULES} >= {
        "resistance_training",
        "physical_activity",
        "fat_loss",
        "protein",
        "diet_quality",
    }
    assert all(rule.source_url.startswith("https://") for rule in COACHING_RULES)
