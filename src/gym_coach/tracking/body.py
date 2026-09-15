from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, Field, model_validator

from gym_coach.nutrition.schemas import NutritionModel


class BodyMeasurementObservation(NutritionModel):
    external_id: UUID
    measured_at: AwareDatetime
    measured_on: date
    timezone: str = Field(max_length=100)
    source: Literal["health_connect_openscale"] = "health_connect_openscale"
    weight_kg: Decimal = Field(ge=25, le=500)
    body_fat_percent: Decimal | None = Field(default=None, ge=2, le=70)
    body_fat_method: Literal["consumer_bia"] | None = None
    lean_body_mass_kg: Decimal | None = Field(default=None, ge=10, le=400)
    body_water_mass_kg: Decimal | None = Field(default=None, ge=5, le=300)
    bone_mass_kg: Decimal | None = Field(default=None, ge=0.1, le=20)
    basal_metabolic_rate_kcal: Decimal | None = Field(default=None, ge=300, le=10_000)
    observed_at: AwareDatetime

    @model_validator(mode="after")
    def valid_dates(self) -> "BodyMeasurementObservation":
        try:
            zone = ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown timezone") from exc
        if self.measured_on != self.measured_at.astimezone(zone).date():
            raise ValueError("Body measurement local date does not match its timestamp")
        if self.measured_at > self.observed_at:
            raise ValueError("Body measurement cannot follow its observation")
        return self


class BodyMeasurementTrend(NutritionModel):
    metric: Literal["weight_kg", "body_fat_percent"]
    recent_count: int
    previous_count: int
    recent_mean: Decimal | None
    previous_mean: Decimal | None
    change: Decimal | None


def body_measurement_trends(
    rows: list[BodyMeasurementObservation], end: date
) -> list[BodyMeasurementTrend]:
    first_by_day: dict[date, BodyMeasurementObservation] = {}
    for row in sorted(rows, key=lambda item: item.measured_at):
        first_by_day.setdefault(row.measured_on, row)
    daily = list(first_by_day.values())
    result = []
    for metric in ("weight_kg", "body_fat_percent"):
        recent = [
            value
            for row in daily
            if end - timedelta(days=6) <= row.measured_on <= end
            and (value := getattr(row, metric)) is not None
        ]
        previous = [
            value
            for row in daily
            if end - timedelta(days=13) <= row.measured_on < end - timedelta(days=6)
            and (value := getattr(row, metric)) is not None
        ]
        recent_mean = _mean(recent)
        previous_mean = _mean(previous)
        result.append(
            BodyMeasurementTrend(
                metric=metric,
                recent_count=len(recent),
                previous_count=len(previous),
                recent_mean=recent_mean,
                previous_mean=previous_mean,
                change=(
                    _rounded(recent_mean - previous_mean)
                    if recent_mean is not None
                    and previous_mean is not None
                    and min(len(recent), len(previous)) >= 3
                    else None
                ),
            )
        )
    return result


def _mean(values: list[Decimal]) -> Decimal | None:
    return _rounded(sum(values, Decimal(0)) / len(values)) if values else None


def _rounded(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
