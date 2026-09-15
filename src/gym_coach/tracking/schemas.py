from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field

from gym_coach.mcp.schemas import (
    AthleteCheckInView,
    AthleteMeasurementView,
    ExerciseProgressReport,
    TrainingWorkout,
)
from gym_coach.metrics.types import MetricsSummary
from gym_coach.nutrition.schemas import Nutrients, NutritionModel
from gym_coach.tracking.activity import ActivitySummary
from gym_coach.tracking.body import BodyMeasurementObservation, BodyMeasurementTrend
from gym_coach.tracking.training import WorkoutComparison


class TargetParameters(NutritionModel):
    effective_from: date
    activity_factor: Decimal = Field(ge=Decimal("1.2"), le=Decimal("2.5"))
    energy_adjustment_percent: Decimal = Field(ge=-20, le=15)
    protein_g_per_kg: Decimal = Field(ge=Decimal("1.4"), le=Decimal("2.0"))
    fat_energy_percent: Decimal = Field(ge=20, le=35)
    fiber_g_per_1000_kcal: Decimal = Field(default=Decimal("14"), ge=10, le=20)
    rationale: str = Field(min_length=10, max_length=1000)


class TargetPreview(NutritionModel):
    parameters: TargetParameters
    calculation_policy: Literal["adult_targets_v1", "adult_targets_v2"] = "adult_targets_v2"
    goal_ids: list[UUID]
    profile_version: int
    weight_measured_on: date
    weight_kg: Decimal
    resting_energy_kcal: int
    estimated_maintenance_kcal: Decimal
    daily: Nutrients
    fingerprint: str
    limitations: list[str]


class TargetVersion(TargetPreview):
    id: UUID


class DayClosure(NutritionModel):
    day: date
    timezone: str = "Europe/Madrid"
    complete: bool
    diary_fingerprint: str


class NutritionDifference(NutritionModel):
    energy_kcal: Decimal
    protein_g: Decimal
    carbohydrate_g: Decimal
    fat_g: Decimal
    fiber_g: Decimal | None


class NutritionDayReview(NutritionModel):
    day: date
    logged: Nutrients
    has_estimates: bool
    complete: bool
    diary_fingerprint: str
    target: TargetVersion | None
    difference: NutritionDifference | None


class MeasurementTrend(NutritionModel):
    metric: Literal["weight_kg", "waist_cm"]
    recent_count: int
    previous_count: int
    recent_mean: Decimal | None
    previous_mean: Decimal | None
    change: Decimal | None


class WeeklyReview(NutritionModel):
    end_day: date
    timezone: str
    days: list[NutritionDayReview]
    complete_days: int
    mean_complete_day_intake: Nutrients | None
    mean_target_difference: NutritionDifference | None
    measurements: list[AthleteMeasurementView]
    wearable_measurements: list[BodyMeasurementObservation]
    wearable_trends: list[BodyMeasurementTrend]
    check_ins: list[AthleteCheckInView]
    training: MetricsSummary | None
    activity: ActivitySummary
    trends: list[MeasurementTrend]
    limitations: list[str]
    review_actions: list[str]


class WorkoutCoachingReview(NutritionModel):
    workout: TrainingWorkout
    comparison: WorkoutComparison
    exercise_progress: list[ExerciseProgressReport]
    activity: ActivitySummary
    flags: list[str]
    follow_up_questions: list[str]
    limitations: list[str]
