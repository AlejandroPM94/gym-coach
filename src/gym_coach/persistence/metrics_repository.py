from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from gym_coach.metrics.types import ExercisePerformance, SetSample, WorkoutOccurrence
from gym_coach.persistence.models import (
    ExerciseTemplate,
    Workout,
    WorkoutExercise,
)


class MetricsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_history(
        self, *, since: datetime
    ) -> tuple[tuple[WorkoutOccurrence, ...], tuple[ExercisePerformance, ...]]:
        template_rows = (
            await self._session.execute(
                select(ExerciseTemplate.external_id, ExerciseTemplate.exercise_type)
            )
        ).all()
        templates: dict[str, str] = {
            external_id: exercise_type for external_id, exercise_type in template_rows
        }
        workouts = (
            await self._session.scalars(
                select(Workout)
                .where(Workout.deleted_at.is_(None), Workout.start_time > since)
                .options(selectinload(Workout.exercises).selectinload(WorkoutExercise.sets))
                .order_by(Workout.start_time)
            )
        ).all()
        occurrences = tuple(
            WorkoutOccurrence(
                external_id=item.external_id,
                performed_at=item.start_time,
                routine_external_id=item.routine_external_id,
            )
            for item in workouts
        )
        performances = tuple(
            ExercisePerformance(
                workout_external_id=workout.external_id,
                exercise_template_external_id=exercise.exercise_template_external_id,
                exercise_type=templates.get(exercise.exercise_template_external_id, "unknown"),
                performed_at=workout.start_time,
                sets=tuple(
                    SetSample(
                        position=item.position,
                        set_type=item.set_type,
                        weight_kg=item.weight_kg,
                        reps=item.reps,
                        distance_meters=item.distance_meters,
                        duration_seconds=item.duration_seconds,
                        rpe=item.rpe,
                    )
                    for item in exercise.sets
                ),
            )
            for workout in workouts
            for exercise in workout.exercises
        )
        return occurrences, performances
