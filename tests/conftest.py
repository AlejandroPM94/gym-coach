from collections.abc import AsyncIterator

import httpx
import pytest

from gym_coach.integrations.hevy.client import HevyClient


@pytest.fixture
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url="https://hevy.test") as client:
        yield client


@pytest.fixture
def hevy_client(http_client: httpx.AsyncClient) -> HevyClient:
    return HevyClient("test-placeholder", http_client=http_client)
