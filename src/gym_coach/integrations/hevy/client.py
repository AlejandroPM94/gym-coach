import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
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
    RoutineResponse,
    RoutineWriteRequest,
    UserInfo,
    UserInfoResponse,
    Workout,
    WorkoutEvent,
    WorkoutEventPage,
    WorkoutPage,
)

ModelT = TypeVar("ModelT", bound=BaseModel)
PageT = TypeVar("PageT", bound=PageMetadata)


class HevyClient:
    """Adapter for Hevy; callers own approval and idempotency for write operations."""

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
        params: dict[str, int | str] | None = None,
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

    async def _write(
        self,
        method: str,
        path: str,
        request: RoutineWriteRequest,
        *,
        resource: str,
        include_null_folder_id: bool,
    ) -> Routine:
        request_payload = request.model_dump(mode="json", by_alias=True, exclude_none=True)
        if include_null_folder_id:
            # Hevy distinguishes an omitted folder from the explicit null that selects
            # the account's default "My Routines" folder on routine creation.
            request_payload["routine"]["folder_id"] = request.routine.folder_id
        try:
            response = await self._http.request(
                method,
                path,
                json=request_payload,
            )
        except httpx.TimeoutException as exc:
            raise HevyTimeoutError(
                "Hevy write timed out; the remote outcome is unknown and was not retried"
            ) from exc
        except httpx.RequestError as exc:
            raise HevyTransportError(
                "Hevy write transport failed; the remote outcome is unknown and was not retried"
            ) from exc
        if response.is_error:
            raise HevyHTTPError(response.status_code, self._safe_http_message(response.status_code))
        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise HevyInvalidResponseError("Hevy returned invalid JSON after a write") from exc
        if self._raw_store is not None:
            self._raw_store.save(resource, payload)
        try:
            if isinstance(payload, dict) and "routine" in payload:
                return RoutineResponse.model_validate(payload).routine
            return Routine.model_validate(payload)
        except ValidationError as exc:
            raise HevyInvalidResponseError(
                "Hevy write response did not match its expected schema: "
                f"{sanitized_validation_details(exc)}"
            ) from exc

    @staticmethod
    def _safe_http_message(status_code: int) -> str:
        if status_code == 401:
            return "Hevy rejected the credentials"
        if status_code == 403:
            return "Hevy rejected the operation due to permissions, plan, or account limits"
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

    async def get_routine(self, routine_id: str) -> Routine:
        response = await self._get(
            f"/v1/routines/{routine_id}",
            RoutineResponse,
            resource="routine",
        )
        return response.routine

    async def create_routine(self, request: RoutineWriteRequest) -> Routine:
        before_ids = {routine.id for routine in await self.get_all_routines()}
        try:
            return await self._write(
                "POST",
                "/v1/routines",
                request,
                resource="routine_created",
                include_null_folder_id=True,
            )
        except HevyInvalidResponseError as exc:
            # A 2xx response with an undocumented body can still mean that Hevy
            # created the routine. Recover only when one newly observed routine
            # matches the exact request; ambiguity remains an uncertain outcome.
            matches = [
                routine
                for routine in await self.get_all_routines()
                if routine.id not in before_ids and routine_matches_write_request(routine, request)
            ]
            if len(matches) == 1:
                return matches[0]
            raise exc

    async def update_routine(self, routine_id: str, request: RoutineWriteRequest) -> Routine:
        return await self._write(
            "PUT",
            f"/v1/routines/{routine_id}",
            request,
            resource="routine_updated",
            include_null_folder_id=False,
        )

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

    async def iter_workout_event_pages(
        self, *, since: datetime, page_size: int = 10
    ) -> AsyncIterator[WorkoutEventPage]:
        since_value = since.isoformat().replace("+00:00", "Z")
        page_number = 1
        while True:
            page = await self._get(
                "/v1/workouts/events",
                WorkoutEventPage,
                resource="workout_events",
                params={"page": page_number, "pageSize": page_size, "since": since_value},
            )
            yield page
            if page.page >= page.page_count:
                break
            if page.page != page_number:
                raise HevyInvalidResponseError("Hevy returned inconsistent pagination metadata")
            page_number += 1

    async def get_workout_events(self, *, since: datetime) -> list[WorkoutEvent]:
        return [
            event
            async for page in self.iter_workout_event_pages(since=since)
            for event in page.events
        ]

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


def routine_matches_write_request(routine: Routine, request: RoutineWriteRequest) -> bool:
    """Compare fields controlled by gym-coach and ignore Hevy-generated metadata."""
    expected = request.routine
    if routine.title != expected.title or routine.folder_id != expected.folder_id:
        return False
    if len(routine.exercises) != len(expected.exercises):
        return False
    for actual_exercise, expected_exercise in zip(
        routine.exercises, expected.exercises, strict=True
    ):
        if (
            actual_exercise.exercise_template_id != expected_exercise.exercise_template_id
            or actual_exercise.superset_id != expected_exercise.superset_id
            or actual_exercise.rest_seconds != expected_exercise.rest_seconds
            or (actual_exercise.notes or None) != (expected_exercise.notes or None)
            or len(actual_exercise.sets) != len(expected_exercise.sets)
        ):
            return False
        for actual_set, expected_set in zip(
            actual_exercise.sets, expected_exercise.sets, strict=True
        ):
            if (
                actual_set.set_type != expected_set.set_type
                or actual_set.weight_kg != expected_set.weight_kg
                or actual_set.reps != expected_set.reps
                or actual_set.distance_meters != expected_set.distance_meters
                or actual_set.duration_seconds != expected_set.duration_seconds
                or actual_set.custom_metric != expected_set.custom_metric
                or actual_set.rep_range != expected_set.rep_range
            ):
                return False
    return True
