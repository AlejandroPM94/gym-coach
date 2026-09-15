import hashlib
import json
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from gym_coach.mcp.schemas import AthleteMeasurementView
from gym_coach.nutrition.schemas import Nutrients
from gym_coach.tracking.schemas import MeasurementTrend, NutritionDifference, TargetParameters


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def rounded(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_target(
    resting: int, weight: Decimal, params: TargetParameters
) -> tuple[Decimal, Nutrients]:
    maintenance = rounded(Decimal(resting) * params.activity_factor)
    energy = rounded(maintenance * (1 + params.energy_adjustment_percent / 100))
    protein = rounded(weight * params.protein_g_per_kg)
    fat = rounded(energy * params.fat_energy_percent / 100 / 9)
    carbs = rounded((energy - protein * 4 - fat * 9) / 4)
    fiber = rounded(energy / 1000 * params.fiber_g_per_1000_kcal)
    # Product scope guardrails, not a diagnosis or universal prescription.
    if energy < 1200 or carbs < 130:
        raise ValueError(
            "Target outside general-nutrition scope; review parameters with a professional"
        )
    return maintenance, Nutrients(
        energy_kcal=energy,
        protein_g=protein,
        fat_g=fat,
        carbohydrate_g=carbs,
        fiber_g=fiber,
    )


def difference(intake: Nutrients, target: Nutrients) -> NutritionDifference:
    return NutritionDifference(
        energy_kcal=intake.energy_kcal - target.energy_kcal,
        protein_g=intake.protein_g - target.protein_g,
        carbohydrate_g=intake.carbohydrate_g - target.carbohydrate_g,
        fat_g=intake.fat_g - target.fat_g,
        fiber_g=(
            intake.fiber_g - target.fiber_g
            if intake.fiber_g is not None and target.fiber_g is not None
            else None
        ),
    )


def measurement_trends(rows: list[AthleteMeasurementView], end: date) -> list[MeasurementTrend]:
    result = []
    for metric in ("weight_kg", "waist_cm"):
        recent = [
            getattr(r, metric)
            for r in rows
            if end - timedelta(days=6) <= r.measured_on <= end and getattr(r, metric) is not None
        ]
        previous = [
            getattr(r, metric)
            for r in rows
            if end - timedelta(days=13) <= r.measured_on < end - timedelta(days=6)
            and getattr(r, metric) is not None
        ]
        recent_mean = rounded(sum(recent, Decimal(0)) / len(recent)) if recent else None
        previous_mean = rounded(sum(previous, Decimal(0)) / len(previous)) if previous else None
        # Weight needs repeated observations; waist is often measured only weekly.
        minimum = 3 if metric == "weight_kg" else 1
        change = (
            rounded(recent_mean - previous_mean)
            if recent_mean is not None
            and previous_mean is not None
            and min(len(recent), len(previous)) >= minimum
            else None
        )
        result.append(
            MeasurementTrend(
                metric=metric,
                recent_count=len(recent),
                previous_count=len(previous),
                recent_mean=recent_mean,
                previous_mean=previous_mean,
                change=change,
            )
        )
    return result
