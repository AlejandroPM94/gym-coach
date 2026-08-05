import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gym_coach.integrations.hevy.client import HevyClient
from gym_coach.integrations.hevy.errors import HevyError
from gym_coach.integrations.hevy.schemas import (
    Exercise,
    ExerciseTemplate,
    HevySet,
    Routine,
    UserInfo,
    Workout,
)
from gym_coach.persistence.hevy_repository import HevyRepository
from gym_coach.sync.types import (
    ExerciseTemplateRecord,
    HevySnapshot,
    NormalizedExercise,
    NormalizedSet,
    RoutineRecord,
    SyncResult,
    UserRecord,
    WorkoutRecord,
)


class HevySyncError(Exception):
    """A complete and safe Hevy snapshot could not be built."""


class HevySyncService:
    def __init__(
        self,
        client: HevyClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._client = client
        self._session_factory = session_factory

    async def sync(self) -> SyncResult:
        run_id = uuid4()
        try:
            async with self._session_factory() as session, session.begin():
                await HevyRepository(session).create_run(run_id)
            snapshot = await self._download_snapshot()
            async with self._session_factory() as session, session.begin():
                counts = await HevyRepository(session).apply_snapshot(run_id, snapshot)
        except Exception as exc:
            await self._record_failure_safely(run_id, type(exc).__name__)
            if isinstance(exc, (HevyError, HevySyncError)):
                raise
            raise HevySyncError("Hevy synchronization failed") from exc
        return SyncResult(run_id=str(run_id), counts=counts)

    async def _download_snapshot(self) -> HevySnapshot:
        user = await self._client.get_user()
        templates = await self._client.get_all_exercise_templates()
        routines = await self._client.get_all_routines()
        workouts = await self._client.get_all_workouts()
        return HevySnapshot(
            user=_map_user(user),
            exercise_templates=tuple(_map_template(item) for item in templates),
            routines=tuple(_map_routine(item) for item in routines),
            workouts=tuple(_map_workout(item) for item in workouts),
            completed_at=datetime.now(UTC),
        )

    async def _record_failure(self, run_id: UUID, error_type: str) -> None:
        async with self._session_factory() as session, session.begin():
            await HevyRepository(session).mark_run_failed(run_id, error_type)

    async def _record_failure_safely(self, run_id: UUID, error_type: str) -> None:
        try:
            await self._record_failure(run_id, error_type)
        except SQLAlchemyError:
            # The primary exception remains the useful boundary error when the database is down.
            return


def _map_user(user: UserInfo) -> UserRecord:
    if user.id is None:
        raise HevySyncError("Hevy user response is missing its stable identifier")
    values = {"external_id": user.id, "name": user.name, "profile_url": user.url}
    return UserRecord(
        external_id=user.id,
        name=user.name,
        profile_url=user.url,
        content_hash=_hash(values),
    )


def _map_template(template: ExerciseTemplate) -> ExerciseTemplateRecord:
    values = {
        "external_id": template.id,
        "title": template.title,
        "exercise_type": template.type,
        "primary_muscle_group": template.primary_muscle_group,
        "secondary_muscle_groups": tuple(template.secondary_muscle_groups),
        "equipment": template.equipment,
        "is_custom": template.is_custom,
    }
    return ExerciseTemplateRecord(
        external_id=template.id,
        title=template.title,
        exercise_type=template.type,
        primary_muscle_group=template.primary_muscle_group,
        secondary_muscle_groups=tuple(template.secondary_muscle_groups),
        equipment=template.equipment,
        is_custom=template.is_custom,
        content_hash=_hash(values),
    )


def _map_routine(routine: Routine) -> RoutineRecord:
    exercises = tuple(_map_exercise(item) for item in routine.exercises)
    values = {
        "external_id": routine.id,
        "title": routine.title,
        "folder_id": routine.folder_id,
        "source_created_at": routine.created_at,
        "source_updated_at": routine.updated_at,
        "exercises": exercises,
    }
    return RoutineRecord(
        external_id=routine.id,
        title=routine.title,
        folder_id=routine.folder_id,
        source_created_at=routine.created_at,
        source_updated_at=routine.updated_at,
        exercises=exercises,
        content_hash=_hash(values),
    )


def _map_workout(workout: Workout) -> WorkoutRecord:
    exercises = tuple(_map_exercise(item) for item in workout.exercises)
    values = {
        "external_id": workout.id,
        "title": workout.title,
        "description": workout.description,
        "routine_external_id": workout.routine_id,
        "start_time": workout.start_time,
        "end_time": workout.end_time,
        "source_created_at": workout.created_at,
        "source_updated_at": workout.updated_at,
        "exercises": exercises,
    }
    return WorkoutRecord(
        external_id=workout.id,
        title=workout.title,
        description=workout.description,
        routine_external_id=workout.routine_id,
        start_time=workout.start_time,
        end_time=workout.end_time,
        source_created_at=workout.created_at,
        source_updated_at=workout.updated_at,
        exercises=exercises,
        content_hash=_hash(values),
    )


def _map_exercise(exercise: Exercise) -> NormalizedExercise:
    return NormalizedExercise(
        position=exercise.index or 0,
        title=exercise.title,
        notes=exercise.notes,
        exercise_template_external_id=exercise.exercise_template_id,
        superset_id=exercise.superset_id,
        rest_seconds=exercise.rest_seconds,
        sets=tuple(_map_set(item) for item in exercise.sets),
    )


def _map_set(item: HevySet) -> NormalizedSet:
    return NormalizedSet(
        position=item.index or 0,
        set_type=item.set_type,
        weight_kg=_decimal(item.weight_kg),
        reps=item.reps,
        distance_meters=_decimal(item.distance_meters),
        duration_seconds=item.duration_seconds,
        rpe=item.rpe,
        custom_metric=_decimal(item.custom_metric),
        rep_range_start=item.rep_range.start if item.rep_range else None,
        rep_range_end=item.rep_range.end if item.rep_range else None,
    )


def _decimal(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _hash(values: dict[str, Any]) -> str:
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()
