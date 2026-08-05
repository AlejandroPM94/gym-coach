import asyncio
from collections.abc import AsyncIterator
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, SecretStr, ValidationError

from gym_coach.integrations.hevy.errors import (
    HevyHTTPError,
    HevyInvalidResponseError,
    HevyTimeoutError,
    HevyTransportError,
    sanitized_validation_details,
)
from gym_coach.integrations.hevy.raw_store import RawResponseStore
from gym_coach.integrations.hevy.schemas import (
    ExerciseTemplate,
    ExerciseTemplatePage,
    PageMetadata,
    Routine,
    RoutinePage,
    UserInfo,
    UserInfoResponse,
    Workout,
    WorkoutPage,
)

ModelT = TypeVar("ModelT", bound=BaseModel)
PageT = TypeVar("PageT", bound=PageMetadata)


class HevyClient:
    """Read-only adapter for the unstable public Hevy API."""

    def __init__(
        self,
        api_key: SecretStr | str,
        *,
        base_url: str = "https://api.hevyapp.com",
        timeout_seconds: float = 15.0,
        retry_attempts: int = 3,
        retry_backoff_seconds: float = 0.5,
        raw_store: RawResponseStore | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if retry_attempts < 1:
            raise ValueError("retry_attempts must be at least 1")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative")
        secret = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        self._owns_http_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"api-key": secret, "Accept": "application/json"},
            timeout=httpx.Timeout(timeout_seconds),
        )
        self._raw_store = raw_store
        self._retry_attempts = retry_attempts
        self._retry_backoff_seconds = retry_backoff_seconds

    async def __aenter__(self) -> "HevyClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http.aclose()

    async def _get(
        self,
        path: str,
        model: type[ModelT],
        *,
        resource: str,
        params: dict[str, int] | None = None,
    ) -> ModelT:
        response: httpx.Response | None = None
        for attempt in range(self._retry_attempts):
            try:
                response = await self._http.get(path, params=params)
            except httpx.TimeoutException as exc:
                if attempt + 1 == self._retry_attempts:
                    raise HevyTimeoutError("Hevy request timed out") from exc
                await self._retry_delay(attempt)
                continue
            except httpx.RequestError as exc:
                if attempt + 1 == self._retry_attempts:
                    raise HevyTransportError("Could not communicate with Hevy") from exc
                await self._retry_delay(attempt)
                continue
            if response.status_code not in {429, 500, 502, 503, 504}:
                break
            if attempt + 1 < self._retry_attempts:
                await self._retry_delay(attempt)
        if response is None:  # pragma: no cover - loop always runs after validated configuration
            raise HevyTransportError("Could not communicate with Hevy")

        if response.is_error:
            message = self._safe_http_message(response.status_code)
            raise HevyHTTPError(response.status_code, message)
        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise HevyInvalidResponseError("Hevy returned invalid JSON") from exc
        if self._raw_store is not None:
            self._raw_store.save(resource, payload)
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise HevyInvalidResponseError(
                "Hevy response did not match its expected schema: "
                f"{sanitized_validation_details(exc)}"
            ) from exc

    async def _retry_delay(self, attempt: int) -> None:
        await asyncio.sleep(self._retry_backoff_seconds * (2**attempt))

    @staticmethod
    def _safe_http_message(status_code: int) -> str:
        if status_code in {401, 403}:
            return "Hevy rejected the credentials"
        if status_code == 429:
            return "Hevy rate limit exceeded"
        if status_code >= 500:
            return "Hevy service error"
        return f"Hevy request failed with HTTP {status_code}"

    async def get_user(self) -> UserInfo:
        response = await self._get("/v1/user/info", UserInfoResponse, resource="user")
        return response.data

    async def iter_routine_pages(self, *, page_size: int = 10) -> AsyncIterator[RoutinePage]:
        async for page in self._iter_pages("/v1/routines", RoutinePage, "routines", page_size):
            yield page

    async def get_all_routines(self) -> list[Routine]:
        return [item async for page in self.iter_routine_pages() for item in page.routines]

    async def iter_workout_pages(self, *, page_size: int = 10) -> AsyncIterator[WorkoutPage]:
        async for page in self._iter_pages("/v1/workouts", WorkoutPage, "workouts", page_size):
            yield page

    async def get_recent_workouts(self, limit: int = 10) -> list[Workout]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        workouts: list[Workout] = []
        async for page in self.iter_workout_pages(page_size=min(limit, 10)):
            workouts.extend(page.workouts)
            if len(workouts) >= limit:
                break
        return workouts[:limit]

    async def get_all_workouts(self) -> list[Workout]:
        return [item async for page in self.iter_workout_pages() for item in page.workouts]

    async def iter_exercise_template_pages(
        self, *, page_size: int = 100
    ) -> AsyncIterator[ExerciseTemplatePage]:
        async for page in self._iter_pages(
            "/v1/exercise_templates",
            ExerciseTemplatePage,
            "exercise_templates",
            page_size,
        ):
            yield page

    async def get_all_exercise_templates(self) -> list[ExerciseTemplate]:
        return [
            item
            async for page in self.iter_exercise_template_pages()
            for item in page.exercise_templates
        ]

    async def _iter_pages(
        self,
        path: str,
        model: type[PageT],
        resource: str,
        page_size: int,
    ) -> AsyncIterator[PageT]:
        page_number = 1
        while True:
            page = await self._get(
                path,
                model,
                resource=resource,
                params={"page": page_number, "pageSize": page_size},
            )
            yield page
            current_page = page.page
            page_count = page.page_count
            if current_page >= page_count:
                break
            if current_page != page_number:
                raise HevyInvalidResponseError("Hevy returned inconsistent pagination metadata")
            page_number += 1
