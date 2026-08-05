import httpx
import pytest
import respx

from gym_coach.integrations.hevy.client import HevyClient
from gym_coach.integrations.hevy.errors import (
    HevyHTTPError,
    HevyInvalidResponseError,
    HevyTimeoutError,
)

USER = {"user": {"id": "user-1", "username": "athlete"}}
WORKOUT = {
    "id": "workout-1",
    "title": "Strength",
    "start_time": "2026-08-01T10:00:00Z",
    "end_time": "2026-08-01T11:00:00Z",
    "exercises": [],
}


@respx.mock
async def test_get_user(hevy_client: HevyClient) -> None:
    respx.get("https://hevy.test/v1/user/info").mock(return_value=httpx.Response(200, json=USER))
    user = await hevy_client.get_user()
    assert user.username == "athlete"


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
    with pytest.raises(HevyInvalidResponseError, match="expected schema"):
        await hevy_client.get_user()


@respx.mock
async def test_timeout(hevy_client: HevyClient) -> None:
    respx.get("https://hevy.test/v1/user/info").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(HevyTimeoutError, match="timed out"):
        await hevy_client.get_user()


def test_owned_client_does_not_expose_key() -> None:
    client = HevyClient("super-secret")
    try:
        assert "super-secret" not in repr(client)
    finally:
        import asyncio

        asyncio.run(client.close())
