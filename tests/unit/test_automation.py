from datetime import UTC, datetime, timedelta

from gym_coach.automation.service import _is_new_workout
from gym_coach.integrations.hevy.schemas import UpdatedWorkoutEvent, Workout


def _event(*, created_at: datetime | None, end_time: datetime) -> UpdatedWorkoutEvent:
    return UpdatedWorkoutEvent(
        type="updated",
        workout=Workout(
            id="workout-1",
            title="Anonymous workout",
            start_time=end_time - timedelta(hours=1),
            end_time=end_time,
            created_at=created_at,
        ),
    )


def test_new_workout_detection_uses_creation_time_and_safe_fallback() -> None:
    cursor = datetime(2026, 8, 6, 12, tzinfo=UTC)

    assert _is_new_workout(
        _event(created_at=cursor + timedelta(minutes=1), end_time=cursor), cursor
    )
    assert not _is_new_workout(
        _event(created_at=cursor - timedelta(days=1), end_time=cursor), cursor
    )
    assert _is_new_workout(_event(created_at=None, end_time=cursor + timedelta(minutes=1)), cursor)
