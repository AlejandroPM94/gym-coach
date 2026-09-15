from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from gym_coach.persistence.models import (
    ExerciseTemplate,
    ExerciseTemplateSecondaryMuscle,
    HevyUser,
    Routine,
    RoutineExercise,
    RoutineSet,
    RoutineVersion,
    SyncRun,
    Workout,
    WorkoutExercise,
    WorkoutSet,
)
from gym_coach.sync.types import (
    ExerciseTemplateRecord,
    HevySnapshot,
    NormalizedExercise,
    NormalizedSet,
    RoutineRecord,
    SyncCounts,
    UserRecord,
    WorkoutRecord,
)


class HevyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_run(self, run_id: UUID) -> None:
        self._session.add(SyncRun(id=run_id, provider="hevy", mode="full_snapshot"))

    async def mark_run_failed(self, run_id: UUID, error_type: str) -> None:
        await self._session.execute(
            update(SyncRun)
            .where(SyncRun.id == run_id)
            .values(status="failed", finished_at=datetime.now(UTC), error_type=error_type[:128])
        )

    async def apply_snapshot(self, run_id: UUID, snapshot: HevySnapshot) -> SyncCounts:
        counts = SyncCounts()
        counts.add(await self._upsert_user(run_id, snapshot.user, snapshot.completed_at))
        counts.deleted += await self._upsert_templates(
            run_id, snapshot.exercise_templates, snapshot.completed_at, counts
        )
        counts.deleted += await self._upsert_routines(
            run_id, snapshot.routines, snapshot.completed_at, counts
        )
        counts.deleted += await self._upsert_workouts(
            run_id, snapshot.workouts, snapshot.completed_at, counts
        )
        await self._session.execute(
            update(SyncRun)
            .where(SyncRun.id == run_id)
            .values(
                status="succeeded",
                finished_at=datetime.now(UTC),
                inserted_count=counts.inserted,
                updated_count=counts.updated,
                unchanged_count=counts.unchanged,
                deleted_count=counts.deleted,
            )
        )
        return counts

    async def _upsert_user(self, run_id: UUID, record: UserRecord, seen_at: datetime) -> str:
        existing = await self._session.scalar(
            select(HevyUser).where(HevyUser.external_id == record.external_id)
        )
        if existing is None:
            self._session.add(
                HevyUser(
                    external_id=record.external_id,
                    name=record.name,
                    profile_url=record.profile_url,
                    content_hash=record.content_hash,
                    last_seen_at=seen_at,
                    last_seen_sync_id=run_id,
                )
            )
            return "inserted"
        outcome = "unchanged" if existing.content_hash == record.content_hash else "updated"
        existing.name = record.name
        existing.profile_url = record.profile_url
        self._touch(existing, record.content_hash, run_id, seen_at)
        return outcome

    async def _upsert_templates(
        self,
        run_id: UUID,
        records: tuple[ExerciseTemplateRecord, ...],
        seen_at: datetime,
        counts: SyncCounts,
    ) -> int:
        existing = {
            item.external_id: item
            for item in (
                await self._session.scalars(
                    select(ExerciseTemplate).options(
                        selectinload(ExerciseTemplate.secondary_muscles)
                    )
                )
            ).all()
        }
        for record in records:
            item = existing.get(record.external_id)
            if item is None:
                item = ExerciseTemplate(
                    external_id=record.external_id,
                    title=record.title,
                    exercise_type=record.exercise_type,
                    primary_muscle_group=record.primary_muscle_group,
                    equipment=record.equipment,
                    is_custom=record.is_custom,
                    content_hash=record.content_hash,
                    last_seen_at=seen_at,
                    last_seen_sync_id=run_id,
                )
                item.secondary_muscles = self._secondary_muscles(record)
                self._session.add(item)
                counts.add("inserted")
            else:
                content_changed = item.content_hash != record.content_hash
                outcome = (
                    "unchanged" if not content_changed and item.deleted_at is None else "updated"
                )
                if content_changed:
                    item.secondary_muscles.clear()
                    await self._session.flush()
                    item.title = record.title
                    item.exercise_type = record.exercise_type
                    item.primary_muscle_group = record.primary_muscle_group
                    item.equipment = record.equipment
                    item.is_custom = record.is_custom
                    item.secondary_muscles = self._secondary_muscles(record)
                self._touch(item, record.content_hash, run_id, seen_at)
                counts.add(outcome)
        return self._mark_missing_deleted(
            existing.values(), {r.external_id for r in records}, seen_at, run_id
        )

    async def _upsert_routines(
        self,
        run_id: UUID,
        records: tuple[RoutineRecord, ...],
        seen_at: datetime,
        counts: SyncCounts,
    ) -> int:
        existing = {
            item.external_id: item
            for item in (
                await self._session.scalars(
                    select(Routine).options(
                        selectinload(Routine.exercises).selectinload(RoutineExercise.sets)
                    )
                )
            ).all()
        }
        for record in records:
            await self._store_routine_version(record, seen_at)
            item = existing.get(record.external_id)
            if item is None:
                item = Routine(
                    external_id=record.external_id,
                    title=record.title,
                    folder_id=record.folder_id,
                    source_created_at=record.source_created_at,
                    source_updated_at=record.source_updated_at,
                    content_hash=record.content_hash,
                    last_seen_at=seen_at,
                    last_seen_sync_id=run_id,
                )
                item.exercises = self._routine_exercises(record.exercises)
                self._session.add(item)
                counts.add("inserted")
            else:
                content_changed = item.content_hash != record.content_hash
                outcome = (
                    "unchanged" if not content_changed and item.deleted_at is None else "updated"
                )
                if content_changed:
                    item.exercises.clear()
                    await self._session.flush()
                    item.title = record.title
                    item.folder_id = record.folder_id
                    item.source_created_at = record.source_created_at
                    item.source_updated_at = record.source_updated_at
                    item.exercises = self._routine_exercises(record.exercises)
                self._touch(item, record.content_hash, run_id, seen_at)
                counts.add(outcome)
        return self._mark_missing_deleted(
            existing.values(), {r.external_id for r in records}, seen_at, run_id
        )

    async def _upsert_workouts(
        self,
        run_id: UUID,
        records: tuple[WorkoutRecord, ...],
        seen_at: datetime,
        counts: SyncCounts,
    ) -> int:
        existing = {
            item.external_id: item
            for item in (
                await self._session.scalars(
                    select(Workout).options(
                        selectinload(Workout.exercises).selectinload(WorkoutExercise.sets)
                    )
                )
            ).all()
        }
        versions = list(await self._session.scalars(select(RoutineVersion)))
        for record in records:
            routine_version_id = self._matching_routine_version(record, versions)
            item = existing.get(record.external_id)
            if item is None:
                item = Workout(
                    external_id=record.external_id,
                    title=record.title,
                    description=record.description,
                    routine_external_id=record.routine_external_id,
                    start_time=record.start_time,
                    end_time=record.end_time,
                    source_created_at=record.source_created_at,
                    source_updated_at=record.source_updated_at,
                    content_hash=record.content_hash,
                    last_seen_at=seen_at,
                    last_seen_sync_id=run_id,
                    routine_version_id=routine_version_id,
                )
                item.exercises = self._workout_exercises(record.exercises)
                self._session.add(item)
                counts.add("inserted")
            else:
                content_changed = item.content_hash != record.content_hash
                outcome = (
                    "unchanged" if not content_changed and item.deleted_at is None else "updated"
                )
                if content_changed:
                    item.exercises.clear()
                    await self._session.flush()
                    item.title = record.title
                    item.description = record.description
                    item.routine_external_id = record.routine_external_id
                    item.start_time = record.start_time
                    item.end_time = record.end_time
                    item.source_created_at = record.source_created_at
                    item.source_updated_at = record.source_updated_at
                    item.exercises = self._workout_exercises(record.exercises)
                if item.routine_version_id is None:
                    item.routine_version_id = routine_version_id
                self._touch(item, record.content_hash, run_id, seen_at)
                counts.add(outcome)
        return self._mark_missing_deleted(
            existing.values(), {r.external_id for r in records}, seen_at, run_id
        )

    async def _store_routine_version(self, record: RoutineRecord, seen_at: datetime) -> None:
        exists = await self._session.scalar(
            select(RoutineVersion.id).where(
                RoutineVersion.routine_external_id == record.external_id,
                RoutineVersion.content_hash == record.content_hash,
            )
        )
        if exists is None:
            self._session.add(
                RoutineVersion(
                    routine_external_id=record.external_id,
                    content_hash=record.content_hash,
                    source_updated_at=record.source_updated_at,
                    observed_at=seen_at,
                    payload=self._routine_version_payload(record),
                )
            )
            await self._session.flush()

    @staticmethod
    def _matching_routine_version(
        workout: WorkoutRecord, versions: list[RoutineVersion]
    ) -> UUID | None:
        if workout.routine_external_id is None:
            return None
        eligible = [
            version
            for version in versions
            if version.routine_external_id == workout.routine_external_id
            and version.source_updated_at is not None
            and version.source_updated_at <= workout.start_time
        ]
        if not eligible:
            return None
        return max(
            eligible,
            key=lambda version: (
                version.source_updated_at
                if version.source_updated_at is not None
                else workout.start_time
            ),
        ).id

    @staticmethod
    def _routine_version_payload(record: RoutineRecord) -> dict[str, object]:
        return {
            "external_id": record.external_id,
            "title": record.title,
            "folder_id": record.folder_id,
            "updated_at": record.source_updated_at.isoformat()
            if record.source_updated_at
            else None,
            "exercises": [
                {
                    "position": exercise.position + 1,
                    "exercise_template_external_id": exercise.exercise_template_external_id,
                    "title": exercise.title,
                    "notes": exercise.notes,
                    "rest_seconds": exercise.rest_seconds,
                    "superset_id": exercise.superset_id,
                    "sets": [
                        {
                            "position": item.position + 1,
                            "set_type": item.set_type,
                            "weight_kg": str(item.weight_kg)
                            if item.weight_kg is not None
                            else None,
                            "reps": item.reps,
                            "rep_range_start": item.rep_range_start,
                            "rep_range_end": item.rep_range_end,
                            "distance_meters": str(item.distance_meters)
                            if item.distance_meters is not None
                            else None,
                            "duration_seconds": item.duration_seconds,
                        }
                        for item in exercise.sets
                    ],
                }
                for exercise in record.exercises
            ],
        }

    @staticmethod
    def _touch(
        item: HevyUser | ExerciseTemplate | Routine | Workout,
        content_hash: str,
        run_id: UUID,
        seen_at: datetime,
    ) -> None:
        item.content_hash = content_hash
        item.last_seen_sync_id = run_id
        item.last_seen_at = seen_at
        item.deleted_at = None
        item.deleted_sync_id = None

    @staticmethod
    def _mark_missing_deleted(
        items: Iterable[ExerciseTemplate | Routine | Workout],
        seen_ids: set[str],
        deleted_at: datetime,
        run_id: UUID,
    ) -> int:
        count = 0
        for item in items:
            if item.external_id not in seen_ids and item.deleted_at is None:
                item.deleted_at = deleted_at
                item.deleted_sync_id = run_id
                count += 1
        return count

    @staticmethod
    def _secondary_muscles(
        record: ExerciseTemplateRecord,
    ) -> list[ExerciseTemplateSecondaryMuscle]:
        return [
            ExerciseTemplateSecondaryMuscle(position=index, muscle_group=muscle)
            for index, muscle in enumerate(record.secondary_muscle_groups)
        ]

    @classmethod
    def _routine_exercises(cls, records: tuple[NormalizedExercise, ...]) -> list[RoutineExercise]:
        return [
            RoutineExercise(
                position=record.position,
                title=record.title,
                notes=record.notes,
                exercise_template_external_id=record.exercise_template_external_id,
                superset_id=record.superset_id,
                rest_seconds=record.rest_seconds,
                sets=[cls._routine_set(item) for item in record.sets],
            )
            for record in records
        ]

    @staticmethod
    def _routine_set(record: NormalizedSet) -> RoutineSet:
        return RoutineSet(
            position=record.position,
            set_type=record.set_type,
            weight_kg=record.weight_kg,
            reps=record.reps,
            distance_meters=record.distance_meters,
            duration_seconds=record.duration_seconds,
            custom_metric=record.custom_metric,
            rep_range_start=record.rep_range_start,
            rep_range_end=record.rep_range_end,
        )

    @classmethod
    def _workout_exercises(cls, records: tuple[NormalizedExercise, ...]) -> list[WorkoutExercise]:
        return [
            WorkoutExercise(
                position=record.position,
                title=record.title,
                notes=record.notes,
                exercise_template_external_id=record.exercise_template_external_id,
                superset_id=record.superset_id,
                sets=[cls._workout_set(item) for item in record.sets],
            )
            for record in records
        ]

    @staticmethod
    def _workout_set(record: NormalizedSet) -> WorkoutSet:
        return WorkoutSet(
            position=record.position,
            set_type=record.set_type,
            weight_kg=record.weight_kg,
            reps=record.reps,
            distance_meters=record.distance_meters,
            duration_seconds=record.duration_seconds,
            rpe=record.rpe,
            custom_metric=record.custom_metric,
        )
