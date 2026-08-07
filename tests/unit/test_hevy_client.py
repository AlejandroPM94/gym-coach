import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from gym_coach.integrations.hevy.client import HevyClient
from gym_coach.integrations.hevy.errors import (
    HevyHTTPError,
    HevyInvalidResponseError,
    HevyTimeoutError,
)
from gym_coach.integrations.hevy.schemas import (
    RepRange,
    RoutineWriteData,
    RoutineWriteExercise,
    RoutineWriteRequest,
    RoutineWriteSet,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "hevy"
USER = json.loads((FIXTURES / "user_info.json").read_text(encoding="utf-8"))
WORKOUT = {
    "id": "workout-1",
    "title": "Strength",
    "start_time": "2026-08-01T10:00:00Z",
    "end_time": "2026-08-01T11:00:00Z",
    "exercises": [],
}
ROUTINE = {
    "id": "routine-created",
    "title": "Upper A",
    "folder_id": None,
    "exercises": [
        {
            "index": 0,
            "title": "Anonymous exercise",
            "exercise_template_id": "template-1",
            "rest_seconds": 120,
            "sets": [
                {
                    "index": 0,
                    "type": "normal",
                    "rep_range": {"start": 8, "end": 12},
                }
            ],
        }
    ],
}


def routine_write_request() -> RoutineWriteRequest:
    return RoutineWriteRequest(
        routine=RoutineWriteData(
            title="Upper A",
            exercises=[
                RoutineWriteExercise(
                    exercise_template_id="template-1",
                    rest_seconds=120,
                    sets=[
                        RoutineWriteSet(
                            set_type="normal",
                            rep_range=RepRange(start=8, end=12),
                        )
                    ],
                )
            ],
        )
    )


@respx.mock
async def test_get_user(hevy_client: HevyClient) -> None:
    respx.get("https://hevy.test/v1/user/info").mock(return_value=httpx.Response(200, json=USER))
    user = await hevy_client.get_user()
    assert user.id == "anonymous-user-id"
    assert user.name == "Test Athlete"
    assert user.url == "https://hevy.com/user/test-athlete"


@pytest.mark.parametrize(
    "data",
    [
        {"id": None, "name": None, "url": None},
        {"id": "anonymous-user-id"},
        {**USER["data"], "new_hevy_field": {"nested": True}},
    ],
)
@respx.mock
async def test_get_user_accepts_nullable_optional_and_extra_fields(
    hevy_client: HevyClient, data: dict[str, object]
) -> None:
    respx.get("https://hevy.test/v1/user/info").mock(
        return_value=httpx.Response(200, json={"data": data, "response_extra": True})
    )
    user = await hevy_client.get_user()
    assert user.id == data.get("id")


@respx.mock
async def test_recent_workouts_paginates(hevy_client: HevyClient) -> None:
    route = respx.get("https://hevy.test/v1/workouts")
    route.side_effect = [
        httpx.Response(200, json={"page": 1, "page_count": 2, "workouts": [WORKOUT]}),
        httpx.Response(
            200,
            json={
                "page": 2,
                "page_count": 2,
                "workouts": [{**WORKOUT, "id": "workout-2"}],
            },
        ),
    ]
    workouts = await hevy_client.get_recent_workouts(limit=2)
    assert [workout.id for workout in workouts] == ["workout-1", "workout-2"]
    assert route.call_count == 2
    assert dict(route.calls[0].request.url.params) == {"page": "1", "pageSize": "2"}


@respx.mock
async def test_workout_events_are_typed_and_paginated(hevy_client: HevyClient) -> None:
    route = respx.get("https://hevy.test/v1/workouts/events")
    route.side_effect = [
        httpx.Response(
            200,
            json={
                "page": 1,
                "page_count": 2,
                "workouts": [
                    {
                        "type": "updated",
                        "workout": {
                            **WORKOUT,
                            "created_at": "2026-08-01T11:00:00Z",
                        },
                    }
                ],
            },
        ),
        httpx.Response(
            200,
            json={
                "page": 2,
                "page_count": 2,
                "workouts": [
                    {
                        "type": "deleted",
                        "id": "deleted-workout",
                        "deleted_at": "2026-08-02T11:00:00Z",
                    }
                ],
            },
        ),
    ]

    events = await hevy_client.get_workout_events(since=datetime(2026, 8, 1, tzinfo=UTC))

    assert [event.type for event in events] == ["updated", "deleted"]
    assert route.call_count == 2
    assert dict(route.calls[0].request.url.params) == {
        "page": "1",
        "pageSize": "10",
        "since": "2026-08-01T00:00:00Z",
    }


@respx.mock
async def test_workout_events_accept_empty_realistic_response(
    hevy_client: HevyClient,
) -> None:
    payload = json.loads((FIXTURES / "workout_events_empty.json").read_text(encoding="utf-8"))
    respx.get("https://hevy.test/v1/workouts/events").mock(
        return_value=httpx.Response(200, json=payload)
    )

    events = await hevy_client.get_workout_events(since=datetime(2026, 8, 1, tzinfo=UTC))

    assert events == []


@respx.mock
async def test_http_error_is_sanitized(hevy_client: HevyClient) -> None:
    respx.get("https://hevy.test/v1/user/info").mock(
        return_value=httpx.Response(401, text="api key was secret-value")
    )
    with pytest.raises(HevyHTTPError, match="rejected the credentials") as raised:
        await hevy_client.get_user()
    assert "secret-value" not in str(raised.value)


@respx.mock
async def test_invalid_json(hevy_client: HevyClient) -> None:
    respx.get("https://hevy.test/v1/user/info").mock(
        return_value=httpx.Response(200, text="not-json")
    )
    with pytest.raises(HevyInvalidResponseError, match="invalid JSON"):
        await hevy_client.get_user()


@respx.mock
async def test_invalid_schema(hevy_client: HevyClient) -> None:
    respx.get("https://hevy.test/v1/user/info").mock(
        return_value=httpx.Response(200, json={"unexpected": True})
    )
    with pytest.raises(HevyInvalidResponseError, match="expected schema") as raised:
        await hevy_client.get_user()
    message = str(raised.value)
    assert "field=data" in message
    assert "expected=field present" in message
    assert "received=missing" in message
    assert "unexpected" not in message


@respx.mock
async def test_invalid_field_type_reports_types_without_value(
    hevy_client: HevyClient,
) -> None:
    sensitive_value = "private-personal-value"
    respx.get("https://hevy.test/v1/user/info").mock(
        return_value=httpx.Response(200, json={"data": {"name": [sensitive_value]}})
    )
    with pytest.raises(HevyInvalidResponseError) as raised:
        await hevy_client.get_user()
    message = str(raised.value)
    assert "field=data.name" in message
    assert "expected=string" in message
    assert "received=array" in message
    assert sensitive_value not in message


@respx.mock
async def test_timeout(hevy_client: HevyClient) -> None:
    respx.get("https://hevy.test/v1/user/info").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(HevyTimeoutError, match="timed out"):
        await hevy_client.get_user()


@respx.mock
async def test_retries_transient_http_errors(hevy_client: HevyClient) -> None:
    route = respx.get("https://hevy.test/v1/user/info")
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(429),
        httpx.Response(200, json=USER),
    ]

    user = await hevy_client.get_user()

    assert user.id == "anonymous-user-id"
    assert route.call_count == 3


@respx.mock
async def test_create_and_update_routine_follow_official_contract(
    hevy_client: HevyClient,
) -> None:
    create = respx.post("https://hevy.test/v1/routines").mock(
        return_value=httpx.Response(201, json={"routine": ROUTINE, "new_field": True})
    )
    update = respx.put("https://hevy.test/v1/routines/routine-created").mock(
        return_value=httpx.Response(200, json={"routine": [ROUTINE]})
    )
    get = respx.get("https://hevy.test/v1/routines/routine-created").mock(
        return_value=httpx.Response(200, json={"routine": ROUTINE})
    )
    respx.get("https://hevy.test/v1/routines").mock(
        return_value=httpx.Response(200, json={"page": 1, "page_count": 1, "routines": []})
    )

    fetched = await hevy_client.get_routine("routine-created")
    created = await hevy_client.create_routine(routine_write_request())
    updated = await hevy_client.update_routine("routine-created", routine_write_request())

    assert fetched.id == created.id == updated.id == "routine-created"
    create_payload = json.loads(create.calls[0].request.content)
    update_payload = json.loads(update.calls[0].request.content)
    assert "folder_id" in create_payload["routine"]
    assert create_payload["routine"]["folder_id"] is None
    assert "folder_id" not in update_payload["routine"]
    assert create_payload["routine"]["exercises"][0]["sets"][0] == {
        "type": "normal",
        "rep_range": {"start": 8, "end": 12},
    }
    assert update.call_count == 1
    assert get.call_count == 1


@respx.mock
async def test_routine_response_rejects_ambiguous_lists(hevy_client: HevyClient) -> None:
    respx.get("https://hevy.test/v1/routines/routine-created").mock(
        return_value=httpx.Response(200, json={"routine": [ROUTINE, ROUTINE]})
    )

    with pytest.raises(HevyInvalidResponseError, match="expected schema"):
        await hevy_client.get_routine("routine-created")


@respx.mock
async def test_write_timeout_is_not_retried(hevy_client: HevyClient) -> None:
    respx.get("https://hevy.test/v1/routines").mock(
        return_value=httpx.Response(200, json={"page": 1, "page_count": 1, "routines": []})
    )
    route = respx.post("https://hevy.test/v1/routines").mock(
        side_effect=httpx.ReadTimeout("uncertain")
    )

    with pytest.raises(HevyTimeoutError, match="outcome is unknown"):
        await hevy_client.create_routine(routine_write_request())

    assert route.call_count == 1


@respx.mock
async def test_write_http_403_is_sanitized_and_keeps_status_code(
    hevy_client: HevyClient,
) -> None:
    respx.get("https://hevy.test/v1/routines").mock(
        return_value=httpx.Response(200, json={"page": 1, "page_count": 1, "routines": []})
    )
    respx.post("https://hevy.test/v1/routines").mock(
        return_value=httpx.Response(403, text="private account detail")
    )

    with pytest.raises(HevyHTTPError) as raised:
        await hevy_client.create_routine(routine_write_request())

    assert raised.value.status_code == 403
    assert "permissions, plan, or account limits" in str(raised.value)
    assert "private account detail" not in str(raised.value)


@respx.mock
async def test_create_recovers_unique_matching_routine_after_invalid_201(
    hevy_client: HevyClient,
) -> None:
    routines = respx.get("https://hevy.test/v1/routines")
    routines.side_effect = [
        httpx.Response(200, json={"page": 1, "page_count": 1, "routines": []}),
        httpx.Response(
            200,
            json={"page": 1, "page_count": 1, "routines": [ROUTINE]},
        ),
    ]
    respx.post("https://hevy.test/v1/routines").mock(
        return_value=httpx.Response(201, json={"unexpected_success_shape": True})
    )

    created = await hevy_client.create_routine(routine_write_request())

    assert created.id == "routine-created"
    assert routines.call_count == 2


@respx.mock
async def test_create_keeps_uncertain_outcome_when_invalid_201_cannot_be_matched(
    hevy_client: HevyClient,
) -> None:
    respx.get("https://hevy.test/v1/routines").mock(
        return_value=httpx.Response(200, json={"page": 1, "page_count": 1, "routines": []})
    )
    respx.post("https://hevy.test/v1/routines").mock(
        return_value=httpx.Response(201, json={"unexpected_success_shape": True})
    )

    with pytest.raises(HevyInvalidResponseError, match="write response"):
        await hevy_client.create_routine(routine_write_request())


def test_owned_client_does_not_expose_key() -> None:
    client = HevyClient("super-secret")
    try:
        assert "super-secret" not in repr(client)
    finally:
        import asyncio

        asyncio.run(client.close())
