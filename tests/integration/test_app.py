import httpx
from pytest import MonkeyPatch

from gym_coach.main import create_app


async def test_health_without_database_or_api_key(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("HEVY_API_KEY", raising=False)
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
