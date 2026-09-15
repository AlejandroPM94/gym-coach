from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, Field, model_validator

from gym_coach.nutrition.schemas import NutritionModel


class ActivityDay(NutritionModel):
    day: date
    timezone: str = Field(max_length=100)
    source: Literal["health_connect_samsung"] = "health_connect_samsung"
    steps: int | None = Field(default=None, ge=0, le=200_000)
    sleep_session_minutes: Decimal | None = Field(default=None, ge=0, le=1500)
    sleep_asleep_minutes: Decimal | None = Field(default=None, ge=0, le=1500)
    sleep_awake_minutes: Decimal | None = Field(default=None, ge=0, le=1500)
    sleep_light_minutes: Decimal | None = Field(default=None, ge=0, le=1500)
    sleep_deep_minutes: Decimal | None = Field(default=None, ge=0, le=1500)
    sleep_rem_minutes: Decimal | None = Field(default=None, ge=0, le=1500)
    sleep_session_count: int | None = Field(default=None, ge=0, le=50)
    main_sleep_start_at: AwareDatetime | None = None
    main_sleep_end_at: AwareDatetime | None = None
    exercise_session_count: int | None = Field(default=None, ge=0, le=100)
    exercise_minutes: Decimal | None = Field(default=None, ge=0, le=1440)
    exercise_minutes_by_type: dict[str, Decimal] | None = None
    distance_meters: Decimal | None = Field(default=None, ge=0, le=500_000)
    total_energy_kcal: Decimal | None = Field(default=None, ge=0, le=20_000)
    heart_rate_sample_count: int | None = Field(default=None, ge=0, le=1_000_000)
    mean_heart_rate_bpm: Decimal | None = Field(default=None, ge=20, le=300)
    min_heart_rate_bpm: int | None = Field(default=None, ge=20, le=300)
    max_heart_rate_bpm: int | None = Field(default=None, ge=20, le=300)
    resting_heart_rate_bpm: Decimal | None = Field(default=None, ge=20, le=250)
    hrv_rmssd_ms: Decimal | None = Field(default=None, ge=0, le=1000)
    oxygen_saturation_sample_count: int | None = Field(default=None, ge=0, le=100_000)
    mean_oxygen_saturation_percent: Decimal | None = Field(default=None, ge=50, le=100)
    min_oxygen_saturation_percent: Decimal | None = Field(default=None, ge=50, le=100)
    vo2_max_ml_min_kg: Decimal | None = Field(default=None, ge=5, le=100)
    observed_at: AwareDatetime

    @model_validator(mode="after")
    def valid_date(self) -> "ActivityDay":
        try:
            zone = ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown timezone") from exc
        if self.day > self.observed_at.astimezone(zone).date():
            raise ValueError("Activity day cannot follow its observation")
        if (self.main_sleep_start_at is None) != (self.main_sleep_end_at is None):
            raise ValueError("Main sleep timestamps must be provided together")
        if (
            self.main_sleep_start_at is not None
            and self.main_sleep_end_at is not None
            and self.main_sleep_end_at <= self.main_sleep_start_at
        ):
            raise ValueError("Main sleep must end after it starts")
        return self


class ActivitySummary(NutritionModel):
    days: list[ActivityDay]
    steps_days: int
    sleep_days: int
    mean_steps: Decimal | None
    mean_sleep_session_minutes: Decimal | None
    mean_sleep_asleep_minutes: Decimal | None
    mean_sleep_deep_minutes: Decimal | None
    mean_sleep_rem_minutes: Decimal | None
    mean_exercise_minutes: Decimal | None
    total_distance_meters: Decimal | None
    mean_resting_heart_rate_bpm: Decimal | None
    mean_hrv_rmssd_ms: Decimal | None
    mean_oxygen_saturation_percent: Decimal | None
    latest_vo2_max_ml_min_kg: Decimal | None
    recovery: "RecoveryAssessment"
    last_observed_at: datetime | None
    limitations: list[str]


class RecoveryMetricTrend(NutritionModel):
    metric: Literal["sleep_asleep_minutes", "resting_heart_rate_bpm", "hrv_rmssd_ms", "steps"]
    recent_days: int
    baseline_days: int
    recent_mean: Decimal | None
    baseline_mean: Decimal | None
    change_percent: Decimal | None
    signal: Literal["stable", "adverse", "favorable", "insufficient"]


class RecoveryAssessment(NutritionModel):
    status: Literal["insufficient", "baseline", "monitor", "possible_strain"]
    adverse_signal_count: int
    trends: list[RecoveryMetricTrend]
    limitations: list[str]


def assess_recovery(days: list[ActivityDay], end: date) -> RecoveryAssessment:
    specs: tuple[
        tuple[
            Literal["sleep_asleep_minutes", "resting_heart_rate_bpm", "hrv_rmssd_ms", "steps"],
            Decimal,
            bool,
        ],
        ...,
    ] = (
        ("sleep_asleep_minutes", Decimal(10), False),
        ("resting_heart_rate_bpm", Decimal(5), True),
        ("hrv_rmssd_ms", Decimal(10), False),
        ("steps", Decimal(20), False),
    )
    trends = []
    for metric, threshold, higher_is_adverse in specs:
        recent = _values(days, metric, end - timedelta(days=6), end)
        baseline = _values(days, metric, end - timedelta(days=27), end - timedelta(days=7))
        recent_mean = _mean(recent)
        baseline_mean = _mean(baseline)
        change = None
        if recent_mean is not None and baseline_mean is not None and baseline_mean != 0:
            change = _rounded((recent_mean - baseline_mean) / baseline_mean * 100)
        if len(recent) < 3 or len(baseline) < 7 or change is None:
            signal: Literal["stable", "adverse", "favorable", "insufficient"] = "insufficient"
        elif abs(change) < threshold:
            signal = "stable"
        elif (change > 0) == higher_is_adverse:
            signal = "adverse"
        else:
            signal = "favorable"
        trends.append(
            RecoveryMetricTrend(
                metric=metric,
                recent_days=len(recent),
                baseline_days=len(baseline),
                recent_mean=recent_mean,
                baseline_mean=baseline_mean,
                change_percent=change,
                signal=signal,
            )
        )
    adverse = sum(item.signal == "adverse" for item in trends[:3])
    available = sum(item.signal != "insufficient" for item in trends[:3])
    status: Literal["insufficient", "baseline", "monitor", "possible_strain"] = (
        "insufficient"
        if available == 0
        else "possible_strain"
        if adverse >= 2
        else "monitor"
        if adverse == 1
        else "baseline"
    )
    return RecoveryAssessment(
        status=status,
        adverse_signal_count=adverse,
        trends=trends,
        limitations=[
            "Compares seven recent complete days with the preceding 21-day personal baseline.",
            "Wearable deviations are context for coaching, not a diagnosis or readiness score.",
            "Training changes still require symptoms, performance context and confirmation.",
        ],
    )


def _values(days: list[ActivityDay], metric: str, start: date, end: date) -> list[Decimal]:
    return [
        Decimal(value)
        for item in days
        if start <= item.day <= end and (value := getattr(item, metric)) is not None
    ]


def _mean(values: list[Decimal]) -> Decimal | None:
    return _rounded(sum(values, Decimal(0)) / len(values)) if values else None


def _rounded(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))
