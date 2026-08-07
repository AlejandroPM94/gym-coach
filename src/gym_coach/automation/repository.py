from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from gym_coach.persistence.models import AutomationCursor, WorkoutReview


class AutomationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def cursor(self, stream: str) -> datetime | None:
        return cast(
            datetime | None,
            await self._session.scalar(
                select(AutomationCursor.cursor_at).where(AutomationCursor.stream == stream)
            ),
        )

    async def initialize_cursor(self, stream: str, cursor_at: datetime) -> bool:
        inserted = await self._session.scalar(
            insert(AutomationCursor)
            .values(stream=stream, cursor_at=cursor_at)
            .on_conflict_do_nothing(index_elements=[AutomationCursor.stream])
            .returning(AutomationCursor.stream)
        )
        return inserted is not None

    async def advance_cursor(self, stream: str, cursor_at: datetime) -> None:
        row = await self._session.get(AutomationCursor, stream, with_for_update=True)
        if row is None:
            raise RuntimeError("automation cursor disappeared")
        if cursor_at > row.cursor_at:
            row.cursor_at = cursor_at

    async def enqueue_workout(self, workout_external_id: str) -> None:
        await self._session.execute(
            insert(WorkoutReview)
            .values(workout_external_id=workout_external_id)
            .on_conflict_do_nothing(index_elements=[WorkoutReview.workout_external_id])
        )

    async def claim_next(self, *, now: datetime, stale_after: timedelta) -> WorkoutReview | None:
        row = await self._session.scalar(
            select(WorkoutReview)
            .where(
                (WorkoutReview.status == "pending")
                | (
                    (WorkoutReview.status == "claimed")
                    & (WorkoutReview.claimed_at < now - stale_after)
                )
            )
            .order_by(WorkoutReview.detected_at, WorkoutReview.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is None:
            return None
        row.status = "claimed"
        row.claimed_at = now
        row.attempt_count += 1
        return row

    async def complete(self, review_id: UUID, *, completed_at: datetime) -> WorkoutReview | None:
        row = await self._session.get(WorkoutReview, review_id, with_for_update=True)
        if row is None or row.status != "claimed":
            return None
        row.status = "completed"
        row.completed_at = completed_at
        return row
