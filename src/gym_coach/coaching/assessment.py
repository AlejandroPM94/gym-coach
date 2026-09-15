from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from gym_coach.mcp.schemas import CoachingRule, TrainingHistoryAssessment


@dataclass(frozen=True, slots=True)
class HistoryFacts:
    period_start: datetime | None
    period_end: datetime | None
    workout_count: int
    active_week_count: int
    distinct_exercise_count: int


def assess_training_history(facts: HistoryFacts, *, as_of: date) -> TrainingHistoryAssessment:
    level: Literal["insufficient", "developing", "established", "extensive"]
    confidence: Literal["low", "medium", "high"]
    if facts.period_start is None or facts.period_end is None:
        calendar_days = 0
    else:
        calendar_days = max((facts.period_end.date() - facts.period_start.date()).days + 1, 1)
    if facts.workout_count < 8 or calendar_days < 28:
        level, confidence = "insufficient", "low"
    elif facts.workout_count < 36 or calendar_days < 120:
        level, confidence = "developing", "medium"
    elif facts.workout_count < 160 or calendar_days < 540:
        level, confidence = "established", "high"
    else:
        level, confidence = "extensive", "high"
    limitations = [
        "Training logs show exposure and consistency, not exercise technique or medical readiness."
    ]
    if facts.workout_count < 8:
        limitations.append("Too few workouts are available for a stable historical assessment.")
    if calendar_days < 90:
        limitations.append("The observed period is shorter than three months.")
    ratio = (
        Decimal(facts.workout_count) / Decimal(facts.active_week_count)
        if facts.active_week_count
        else Decimal(0)
    )
    return TrainingHistoryAssessment(
        evidence_id=f"history:assessment:{as_of.isoformat()}",
        period_start=facts.period_start,
        period_end=facts.period_end,
        calendar_days=calendar_days,
        workout_count=facts.workout_count,
        active_week_count=facts.active_week_count,
        distinct_exercise_count=facts.distinct_exercise_count,
        workouts_per_active_week=str(ratio.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        history_level=level,
        confidence=confidence,
        limitations=limitations,
    )


def calculate_bmi(weight_kg: Decimal, height_cm: Decimal) -> Decimal:
    height_m = height_cm / Decimal(100)
    return (weight_kg / (height_m * height_m)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def calculate_mifflin_st_jeor(
    *, weight_kg: Decimal, height_cm: Decimal, age: int, sex: str
) -> int | None:
    if sex not in {"female", "male"} or not 18 <= age <= 100:
        return None
    sex_constant = Decimal(5) if sex == "male" else Decimal(-161)
    result = Decimal(10) * weight_kg + Decimal("6.25") * height_cm - Decimal(5) * age
    return int((result + sex_constant).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def protein_range(weight_kg: Decimal) -> tuple[int, int]:
    lower = (weight_kg * Decimal("1.4")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    upper = (weight_kg * Decimal("2.0")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(lower), int(upper)


COACHING_RULES: tuple[CoachingRule, ...] = (
    CoachingRule(
        rule_id="acsm.resistance.2026.consistency",
        topic="resistance_training",
        guidance=(
            "Prioritize a sustainable plan that trains all major muscle groups at least twice "
            "weekly; tailor load and volume to the goal instead of adding needless complexity."
        ),
        source_title="ACSM 2026 resistance training guidelines",
        source_url="https://acsm.org/resistance-training-guidelines-update-2026/",
        source_year=2026,
        scope="Healthy adults; individualize for health conditions and sport-specific needs.",
    ),
    CoachingRule(
        rule_id="who.activity.2020.adults",
        topic="physical_activity",
        guidance=(
            "For general health, consider 150-300 minutes of moderate aerobic activity or "
            "75-150 vigorous minutes weekly, plus muscle strengthening on at least two days."
        ),
        source_title="WHO physical activity and sedentary behaviour guidelines",
        source_url="https://www.who.int/publications/i/item/9789240014886",
        source_year=2020,
        scope="Population-level adult health guidance, not an individualized prescription.",
    ),
    CoachingRule(
        rule_id="issn.body_composition.2017.deficit",
        topic="fat_loss",
        guidance=(
            "Fat loss requires a sustained energy deficit; choose a dietary approach the athlete "
            "can adhere to and monitor trends rather than promising spot reduction."
        ),
        source_title="ISSN position stand: diets and body composition",
        source_url="https://pubmed.ncbi.nlm.nih.gov/28630601/",
        source_year=2017,
        scope="Healthy adults; slower loss may better preserve lean mass in leaner athletes.",
    ),
    CoachingRule(
        rule_id="issn.protein.2017.active",
        topic="protein",
        guidance=(
            "For healthy exercising adults, use 1.4-2.0 g protein/kg/day as a general evidence "
            "range and individualize within it."
        ),
        source_title="ISSN position stand: protein and exercise",
        source_url="https://pmc.ncbi.nlm.nih.gov/articles/PMC5477153/",
        source_year=2017,
        scope=(
            "Healthy exercising adults; renal disease or other clinical needs require a clinician."
        ),
    ),
    CoachingRule(
        rule_id="aesan.diet_quality.2022.spain",
        topic="diet_quality",
        guidance=(
            "Base food-quality advice on vegetables, fruit, legumes, whole grains, water and "
            "healthy fats, while limiting processed meat, saturated fat, added sugar and salt."
        ),
        source_title="AESAN healthy and sustainable dietary recommendations",
        source_url=(
            "https://www.aesan.gob.es/AECOSAN/web/nutricion/subseccion/"
            "recomendaciones_dieteticas.htm"
        ),
        source_year=2022,
        scope="General guidance for the Spanish population, adapted to preferences and allergies.",
    ),
)
