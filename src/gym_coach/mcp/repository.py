from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from gym_coach.mcp.schemas import (
    AthleteGoal,
    AthleteSummary,
    CompletedExercise,
    CompletedSet,
    ExerciseTemplateSearchResults,
    ExerciseTemplateSummary,
    PlannedExercise,
    PlannedSet,
    RecentWorkouts,
    RoutineList,
    RoutineSummary,
    TrainingRoutine,
    TrainingWorkout,
    WorkoutSummary,
)
from gym_coach.persistence.models import (
    AthleteProfile,
    ExerciseTemplate,
    HevyUser,
    Routine,
    RoutineExercise,
    TrainingGoal,
    Workout,
    WorkoutExercise,
)


class PostgresMCPRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def is_available(self) -> bool:
        async with self._session_factory() as session:
            await session.execute(select(1))
        return True

    async def athlete_summary(self) -> AthleteSummary:
        async with self._session_factory() as session:
            profile = await session.scalar(
                select(AthleteProfile).where(AthleteProfile.profile_key == "default")
            )
            hevy_available = bool(
                await session.scalar(
                    select(func.count()).select_from(HevyUser).where(HevyUser.deleted_at.is_(None))
                )
            )
            if profile is None:
                return AthleteSummary(
                    source="hevy_sync" if hevy_available else "none",
                    profile_complete=False,
                    hevy_data_available=hevy_available,
                    pending_fields=[
                        "experience_level",
                        "training_days_per_week",
                        "session_duration_minutes",
                        "equipment",
                        "goals",
                    ],
                )
            goals = (
                await session.scalars(
                    select(TrainingGoal)
                    .where(TrainingGoal.profile_id == profile.id, TrainingGoal.status == "active")
                    .order_by(TrainingGoal.priority, TrainingGoal.version)
                )
            ).all()
            pending = []
            if profile.session_duration_minutes is None:
                pending.append("session_duration_minutes")
            if not profile.equipment:
                pending.append("equipment")
            if not goals:
                pending.append("goals")
            return AthleteSummary(
                source="athlete_profile",
                profile_complete=not pending,
                hevy_data_available=hevy_available,
                experience_level=profile.experience_level,
                training_days_per_week=profile.training_days_per_week,
                session_duration_minutes=profile.session_duration_minutes,
                equipment=profile.equipment,
                limitations=profile.limitations,
                preferences=profile.preferences,
                goals=[
                    AthleteGoal(
                        goal_type=goal.goal_type,
                        description=goal.description,
                        priority=goal.priority,
                        target_date=goal.target_date.date() if goal.target_date else None,
                    )
                    for goal in goals
                ],
                pending_fields=pending,
            )

    async def list_routines(self) -> RoutineList:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(Routine)
                    .where(Routine.deleted_at.is_(None))
                    .options(selectinload(Routine.exercises))
                    .order_by(Routine.folder_id.asc().nulls_last(), Routine.title)
                )
            ).all()
        routines = [
            RoutineSummary(
                external_id=row.external_id,
                title=row.title,
                folder_id=row.folder_id,
                position=index,
                exercise_count=len(row.exercises),
            )
            for index, row in enumerate(rows, start=1)
        ]
        return RoutineList(count=len(routines), routines=routines)

    async def get_routine(self, external_id: str) -> TrainingRoutine | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(Routine)
                .where(Routine.external_id == external_id, Routine.deleted_at.is_(None))
                .options(selectinload(Routine.exercises).selectinload(RoutineExercise.sets))
            )
        if row is None:
            return None
        return TrainingRoutine(
            external_id=row.external_id,
            title=row.title,
            folder_id=row.folder_id,
            updated_at=row.source_updated_at,
            exercises=[
                PlannedExercise(
                    position=exercise.position + 1,
                    exercise_template_external_id=exercise.exercise_template_external_id,
                    title=exercise.title,
                    notes=exercise.notes,
                    rest_seconds=exercise.rest_seconds,
                    superset_id=exercise.superset_id,
                    sets=[
                        PlannedSet(
                            position=item.position + 1,
                            set_type=item.set_type,
                            weight_kg=str(item.weight_kg) if item.weight_kg is not None else None,
                            reps=item.reps,
                            rep_range_start=item.rep_range_start,
                            rep_range_end=item.rep_range_end,
                            distance_meters=(
                                str(item.distance_meters)
                                if item.distance_meters is not None
                                else None
                            ),
                            duration_seconds=item.duration_seconds,
                        )
                        for item in exercise.sets
                    ],
                )
                for exercise in row.exercises
            ],
        )

    async def recent_workouts(self, limit: int) -> RecentWorkouts:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(Workout)
                    .where(Workout.deleted_at.is_(None))
                    .options(selectinload(Workout.exercises))
                    .order_by(Workout.start_time.desc())
                    .limit(limit)
                )
            ).all()
        workouts = [
            WorkoutSummary(
                external_id=row.external_id,
                title=row.title,
                start_time=row.start_time,
                end_time=row.end_time,
                routine_external_id=row.routine_external_id,
                exercise_count=len(row.exercises),
            )
            for row in rows
        ]
        return RecentWorkouts(requested_limit=limit, count=len(workouts), workouts=workouts)

    async def get_workout(self, external_id: str) -> TrainingWorkout | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(Workout)
                .where(Workout.external_id == external_id, Workout.deleted_at.is_(None))
                .options(selectinload(Workout.exercises).selectinload(WorkoutExercise.sets))
            )
        if row is None:
            return None
        return TrainingWorkout(
            external_id=row.external_id,
            title=row.title,
            description=row.description,
            routine_external_id=row.routine_external_id,
            start_time=row.start_time,
            end_time=row.end_time,
            exercises=[
                CompletedExercise(
                    position=exercise.position + 1,
                    exercise_template_external_id=exercise.exercise_template_external_id,
                    title=exercise.title,
                    notes=exercise.notes,
                    superset_id=exercise.superset_id,
                    sets=[
                        CompletedSet(
                            position=item.position + 1,
                            set_type=item.set_type,
                            weight_kg=str(item.weight_kg) if item.weight_kg is not None else None,
                            reps=item.reps,
                            distance_meters=(
                                str(item.distance_meters)
                                if item.distance_meters is not None
                                else None
                            ),
                            duration_seconds=item.duration_seconds,
                            rpe=item.rpe,
                        )
                        for item in exercise.sets
                    ],
                )
                for exercise in row.exercises
            ],
        )

    async def search_exercise_templates(
        self, query: str, limit: int
    ) -> ExerciseTemplateSearchResults:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(ExerciseTemplate)
                    .where(
                        ExerciseTemplate.deleted_at.is_(None),
                        func.lower(ExerciseTemplate.title).contains(query.lower(), autoescape=True),
                    )
                    .options(selectinload(ExerciseTemplate.secondary_muscles))
                    .order_by(ExerciseTemplate.title)
                    .limit(limit)
                )
            ).all()
        results = [
            ExerciseTemplateSummary(
                external_id=row.external_id,
                title=row.title,
                exercise_type=row.exercise_type,
                primary_muscle_group=row.primary_muscle_group,
                secondary_muscle_groups=[item.muscle_group for item in row.secondary_muscles],
                equipment=row.equipment,
                is_custom=row.is_custom,
            )
            for row in rows
        ]
        return ExerciseTemplateSearchResults(
            query=query, requested_limit=limit, count=len(results), results=results
        )
