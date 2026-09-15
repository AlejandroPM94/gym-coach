from collections import defaultdict, deque
from decimal import Decimal
from typing import Literal

from gym_coach.mcp.schemas import (
    CompletedExercise,
    CompletedSet,
    PlannedSet,
    TrainingRoutine,
    TrainingWorkout,
)
from gym_coach.nutrition.schemas import NutritionModel


class SetComparison(NutritionModel):
    planned_position: int
    status: Literal["met", "below", "unknown", "missing"]
    dimensions: dict[str, bool | None]
    load_difference_kg: Decimal | None = None


class ExerciseComparison(NutritionModel):
    template_id: str
    occurrence: int
    sets: list[SetComparison]
    extra_sets: int


class WorkoutComparison(NutritionModel):
    workout_id: str
    routine_id: str
    exercises: list[ExerciseComparison]
    extra_exercise_occurrences: int
    met_sets: int
    below_sets: int
    missing_sets: int
    unknown_sets: int
    prescription_source: Literal["historical_snapshot", "current_fallback"]
    limitations: list[str]


def compare_set(plan: PlannedSet, done: CompletedSet | None) -> SetComparison:
    if done is None:
        return SetComparison(planned_position=plan.position, status="missing", dimensions={})
    checks: dict[str, bool | None] = {}
    minimum_reps = plan.rep_range_start if plan.rep_range_start is not None else plan.reps
    for name, expected, actual in (
        ("reps", minimum_reps, done.reps),
        ("duration_seconds", plan.duration_seconds, done.duration_seconds),
        ("distance_meters", plan.distance_meters, done.distance_meters),
    ):
        if expected is not None:
            checks[name] = (
                Decimal(str(actual)) >= Decimal(str(expected)) if actual is not None else None
            )
    status: Literal["met", "below", "unknown"] = (
        "below"
        if False in checks.values()
        else "unknown"
        if not checks or None in checks.values()
        else "met"
    )
    return SetComparison(
        planned_position=plan.position,
        status=status,
        dimensions=checks,
        load_difference_kg=Decimal(done.weight_kg) - Decimal(plan.weight_kg)
        if done.weight_kg is not None and plan.weight_kg is not None
        else None,
    )


def compare_workout(
    plan: TrainingRoutine,
    done: TrainingWorkout,
    *,
    prescription_source: Literal["historical_snapshot", "current_fallback"] = "current_fallback",
) -> WorkoutComparison:
    if done.routine_external_id != plan.external_id:
        raise ValueError("Workout is not linked to this routine")
    remaining: dict[str, deque[CompletedExercise]] = defaultdict(deque)
    for performed_exercise in sorted(done.exercises, key=lambda e: e.position):
        remaining[performed_exercise.exercise_template_external_id].append(performed_exercise)
    comparisons = []
    occurrences: dict[str, int] = defaultdict(int)
    for exercise in sorted(plan.exercises, key=lambda e: e.position):
        key = exercise.exercise_template_external_id
        occurrences[key] += 1
        performed = remaining[key].popleft() if remaining[key] else None
        planned_sets = sorted(
            [s for s in exercise.sets if s.set_type != "warmup"], key=lambda s: s.position
        )
        completed_sets = (
            sorted([s for s in performed.sets if s.set_type != "warmup"], key=lambda s: s.position)
            if performed
            else []
        )
        comparisons.append(
            ExerciseComparison(
                template_id=key,
                occurrence=occurrences[key],
                sets=[
                    compare_set(s, completed_sets[i] if i < len(completed_sets) else None)
                    for i, s in enumerate(planned_sets)
                ],
                extra_sets=max(0, len(completed_sets) - len(planned_sets)),
            )
        )
    statuses = [s.status for e in comparisons for s in e.sets]
    limits = [
        "Matching uses exercise occurrence and non-warmup set order.",
        "Load differences do not imply progression; assistance and exercise type matter.",
        "Met means minima reached; technique, pain and progression readiness are not assessed.",
    ]
    if prescription_source == "current_fallback":
        limits.insert(0, "Historical prescription unavailable; current routine used as fallback.")
    if prescription_source == "current_fallback" and (
        plan.updated_at is None or plan.updated_at > done.start_time
    ):
        limits.append("Historical routine unknown or changed; this is not historical adherence.")
    return WorkoutComparison(
        workout_id=done.external_id,
        routine_id=plan.external_id,
        exercises=comparisons,
        extra_exercise_occurrences=sum(len(v) for v in remaining.values()),
        met_sets=statuses.count("met"),
        below_sets=statuses.count("below"),
        missing_sets=statuses.count("missing"),
        unknown_sets=statuses.count("unknown"),
        prescription_source=prescription_source,
        limitations=limits,
    )
