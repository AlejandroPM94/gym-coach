from collections.abc import Awaitable, Callable
from importlib.metadata import PackageNotFoundError, version
from typing import Protocol, Self

from sqlalchemy.exc import SQLAlchemyError

from gym_coach.config import Settings
from gym_coach.integrations.hevy.errors import HevyError
from gym_coach.integrations.hevy.schemas import UserInfo
from gym_coach.mcp.errors import BackendUnavailableError, ResourceNotFoundError
from gym_coach.mcp.schemas import (
    AthleteSummary,
    ComponentStatus,
    ExerciseTemplateSearchResults,
    HevyConnectionStatus,
    RecentWorkouts,
    RoutineList,
    SystemStatus,
    TrainingRoutine,
    TrainingWorkout,
)

MAX_RECENT_WORKOUTS = 50
MAX_EXERCISE_RESULTS = 25


class HevyStatusClient(Protocol):
    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, *args: object) -> None: ...

    async def get_user(self) -> UserInfo: ...


HevyClientFactory = Callable[[], HevyStatusClient]


class MCPReadRepository(Protocol):
    async def is_available(self) -> bool: ...

    async def athlete_summary(self) -> AthleteSummary: ...

    async def list_routines(self) -> RoutineList: ...

    async def get_routine(self, external_id: str) -> TrainingRoutine | None: ...

    async def recent_workouts(self, limit: int) -> RecentWorkouts: ...

    async def get_workout(self, external_id: str) -> TrainingWorkout | None: ...

    async def search_exercise_templates(
        self, query: str, limit: int
    ) -> ExerciseTemplateSearchResults: ...


class MCPTools:
    def __init__(
        self,
        settings: Settings,
        repository: MCPReadRepository,
        hevy_client_factory: HevyClientFactory,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._hevy_client_factory = hevy_client_factory

    async def get_system_status(self) -> SystemStatus:
        postgres = await self._postgres_status()
        hevy_status = await self.get_hevy_connection_status()
        hevy = ComponentStatus(status=hevy_status.status, detail=hevy_status.detail)
        healthy = postgres.status == "available" and hevy.status == "available"
        return SystemStatus(
            version=_application_version(),
            backend_status="healthy" if healthy else "degraded",
            hevy=hevy,
            postgres=postgres,
        )

    async def get_hevy_connection_status(self) -> HevyConnectionStatus:
        secret = self._settings.hevy_api_key
        if secret is None or not secret.get_secret_value():
            return HevyConnectionStatus(
                configured=False,
                accessible=False,
                status="not_configured",
                detail="HEVY_API_KEY is not configured",
            )
        try:
            async with self._hevy_client_factory() as client:
                await client.get_user()
        except HevyError:
            return HevyConnectionStatus(
                configured=True,
                accessible=False,
                status="unavailable",
                detail="Hevy could not be reached or rejected the request",
            )
        except Exception:
            return HevyConnectionStatus(
                configured=True,
                accessible=False,
                status="unavailable",
                detail="Hevy connection check failed safely",
            )
        return HevyConnectionStatus(
            configured=True,
            accessible=True,
            status="available",
            detail="Hevy is configured and accessible",
        )

    async def get_athlete_summary(self) -> AthleteSummary:
        return await self._database_call(self._repository.athlete_summary)

    async def list_training_routines(self) -> RoutineList:
        return await self._database_call(self._repository.list_routines)

    async def get_training_routine(self, routine_id: str) -> TrainingRoutine:
        normalized_id = _validated_identifier(routine_id, "routine_id")
        result = await self._database_call(lambda: self._repository.get_routine(normalized_id))
        if result is None:
            raise ResourceNotFoundError("Training routine was not found")
        return result

    async def get_recent_workouts(self, limit: int = 10) -> RecentWorkouts:
        if not 1 <= limit <= MAX_RECENT_WORKOUTS:
            raise ValueError(f"limit must be between 1 and {MAX_RECENT_WORKOUTS}")
        return await self._database_call(lambda: self._repository.recent_workouts(limit))

    async def get_workout(self, workout_id: str) -> TrainingWorkout:
        normalized_id = _validated_identifier(workout_id, "workout_id")
        result = await self._database_call(lambda: self._repository.get_workout(normalized_id))
        if result is None:
            raise ResourceNotFoundError("Training workout was not found")
        return result

    async def search_exercise_templates(
        self, query: str, limit: int = 10
    ) -> ExerciseTemplateSearchResults:
        normalized_query = query.strip()
        if len(normalized_query) < 2:
            raise ValueError("query must contain at least 2 non-space characters")
        if len(normalized_query) > 100:
            raise ValueError("query must contain at most 100 characters")
        if not 1 <= limit <= MAX_EXERCISE_RESULTS:
            raise ValueError(f"limit must be between 1 and {MAX_EXERCISE_RESULTS}")
        return await self._database_call(
            lambda: self._repository.search_exercise_templates(normalized_query, limit)
        )

    async def _postgres_status(self) -> ComponentStatus:
        try:
            await self._repository.is_available()
        except SQLAlchemyError:
            return ComponentStatus(
                status="unavailable", detail="PostgreSQL is configured but unavailable"
            )
        except Exception:
            return ComponentStatus(status="unavailable", detail="PostgreSQL check failed safely")
        return ComponentStatus(status="available", detail="PostgreSQL is accessible")

    @staticmethod
    async def _database_call[ResultT](operation: Callable[[], Awaitable[ResultT]]) -> ResultT:
        try:
            return await operation()
        except SQLAlchemyError as exc:
            raise BackendUnavailableError("PostgreSQL is unavailable") from exc


def _validated_identifier(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if len(normalized) > 128:
        raise ValueError(f"{field_name} must contain at most 128 characters")
    return normalized


def _application_version() -> str:
    try:
        return version("gym-coach")
    except PackageNotFoundError:
        return "0.1.0"
