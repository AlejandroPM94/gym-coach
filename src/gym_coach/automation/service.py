from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gym_coach.automation.repository import AutomationRepository
from gym_coach.integrations.hevy.client import HevyClient
from gym_coach.integrations.hevy.schemas import UpdatedWorkoutEvent
from gym_coach.sync.hevy import HevySyncService

_STREAM = "hevy_workouts"
_OVERLAP = timedelta(minutes=2)
_CLAIM_TIMEOUT = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class WorkoutReviewGate:
    wake_agent: bool
    review_id: UUID | None = None
    workout_id: str | None = None
    baseline_created: bool = False


class WorkoutReviewAutomationService:
    def __init__(
        self,
        client: HevyClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._client = client
        self._session_factory = session_factory

    async def poll(self, *, now: datetime | None = None) -> WorkoutReviewGate:
        checked_at = now or datetime.now(UTC)
        claimed = await self._claim(checked_at)
        if claimed is not None:
            return claimed

        async with self._session_factory.begin() as session:
            repository = AutomationRepository(session)
            cursor = await repository.cursor(_STREAM)
            if cursor is None:
                initialized = await repository.initialize_cursor(_STREAM, checked_at)
                if initialized:
                    return WorkoutReviewGate(wake_agent=False, baseline_created=True)
                cursor = await repository.cursor(_STREAM)
            if cursor is None:  # pragma: no cover - protected by the transaction above
                raise RuntimeError("could not initialize automation cursor")

        events = await self._client.get_workout_events(since=cursor - _OVERLAP)
        if events:
            await HevySyncService(self._client, self._session_factory).sync()

        new_workout_ids = {
            event.workout.id
            for event in events
            if isinstance(event, UpdatedWorkoutEvent)
            and event.workout.end_time <= checked_at
            and _is_new_workout(event, cursor)
        }
        async with self._session_factory.begin() as session:
            repository = AutomationRepository(session)
            for workout_id in sorted(new_workout_ids):
                await repository.enqueue_workout(workout_id)
            await repository.advance_cursor(_STREAM, checked_at)

        return await self._claim(checked_at) or WorkoutReviewGate(wake_agent=False)

    async def _claim(self, now: datetime) -> WorkoutReviewGate | None:
        async with self._session_factory.begin() as session:
            row = await AutomationRepository(session).claim_next(
                now=now, stale_after=_CLAIM_TIMEOUT
            )
            if row is None:
                return None
            return WorkoutReviewGate(
                wake_agent=True,
                review_id=row.id,
                workout_id=row.workout_external_id,
            )


def _is_new_workout(event: UpdatedWorkoutEvent, cursor: datetime) -> bool:
    created_at = event.workout.created_at
    if created_at is not None:
        return created_at > cursor
    return event.workout.end_time > cursor
