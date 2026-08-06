from datetime import UTC, datetime
from typing import Self

import pytest
from mcp import Client
from pydantic import SecretStr

from gym_coach.config import Settings
from gym_coach.integrations.hevy.errors import HevyHTTPError
from gym_coach.integrations.hevy.schemas import UserInfo
from gym_coach.mcp.schemas import (
    AthleteSummary,
    ExerciseTemplateSearchResults,
    ExerciseTemplateSummary,
    RecentWorkouts,
    RoutineList,
    SystemStatus,
    TrainingRoutine,
    TrainingWorkout,
    WorkoutSummary,
)
from gym_coach.mcp.server import create_mcp_server
from gym_coach.mcp.tools import MAX_EXERCISE_RESULTS, MAX_RECENT_WORKOUTS, MCPTools


class FakeRepository:
    def __init__(self) -> None:
        self.search_arguments: tuple[str, int] | None = None

    async def is_available(self) -> bool:
        return True

    async def athlete_summary(self) -> AthleteSummary:
        return AthleteSummary(
            source="hevy_sync",
            profile_complete=False,
            hevy_data_available=True,
            pending_fields=["goals"],
        )

    async def list_routines(self) -> RoutineList:
        return RoutineList(count=0, routines=[])

    async def get_routine(self, external_id: str) -> TrainingRoutine | None:
        del external_id
        return None

    async def recent_workouts(self, limit: int) -> RecentWorkouts:
        workout = WorkoutSummary(
            external_id="workout-public-id",
            title="Test workout",
            start_time=datetime(2026, 8, 6, 10, tzinfo=UTC),
            end_time=datetime(2026, 8, 6, 11, tzinfo=UTC),
            exercise_count=2,
        )
        return RecentWorkouts(requested_limit=limit, count=1, workouts=[workout])

    async def get_workout(self, external_id: str) -> TrainingWorkout | None:
        del external_id
        return None

    async def search_exercise_templates(
        self, query: str, limit: int
    ) -> ExerciseTemplateSearchResults:
        self.search_arguments = (query, limit)
        result = ExerciseTemplateSummary(
            external_id="template-public-id",
            title="Barbell Bench Press",
            exercise_type="weight_reps",
            primary_muscle_group="chest",
            secondary_muscle_groups=["triceps"],
            equipment="barbell",
            is_custom=False,
        )
        return ExerciseTemplateSearchResults(
            query=query, requested_limit=limit, count=1, results=[result]
        )


class FakeHevyClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    async def get_user(self) -> UserInfo:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return UserInfo(id="not-exposed", name="Private Name", url=None)


def make_tools(
    *, api_key: str | None = None, client: FakeHevyClient | None = None
) -> tuple[MCPTools, FakeRepository, FakeHevyClient]:
    repository = FakeRepository()
    fake_client = client or FakeHevyClient()
    settings = Settings(
        _env_file=None,
        HEVY_API_KEY=SecretStr(api_key) if api_key is not None else None,
    )
    tools = MCPTools(settings, repository, lambda: fake_client)
    return tools, repository, fake_client


async def test_server_initializes_and_enumerates_only_read_tools() -> None:
    tools, _, _ = make_tools()
    server = create_mcp_server(tools)

    registered = await server.list_tools()

    assert {tool.name for tool in registered} == {
        "get_system_status",
        "get_hevy_connection_status",
        "get_athlete_summary",
        "list_training_routines",
        "get_training_routine",
        "get_recent_workouts",
        "get_workout",
        "search_exercise_templates",
    }
    assert all(tool.annotations and tool.annotations.read_only_hint for tool in registered)


async def test_server_validates_arguments_and_enforces_workout_maximum() -> None:
    tools, _, _ = make_tools()
    server = create_mcp_server(tools)

    async with Client(server) as client:
        invalid_type = await client.call_tool("get_recent_workouts", {"limit": "many"})
        over_limit = await client.call_tool(
            "get_recent_workouts", {"limit": MAX_RECENT_WORKOUTS + 1}
        )

    assert invalid_type.is_error
    assert over_limit.is_error
    assert str(MAX_RECENT_WORKOUTS) in str(over_limit.content)


async def test_search_is_trimmed_and_bounded() -> None:
    tools, repository, _ = make_tools()

    result = await tools.search_exercise_templates("  bench  ", limit=MAX_EXERCISE_RESULTS)

    assert repository.search_arguments == ("bench", MAX_EXERCISE_RESULTS)
    assert result.results[0].title == "Barbell Bench Press"
    with pytest.raises(ValueError, match="between 1 and"):
        await tools.search_exercise_templates("bench", limit=MAX_EXERCISE_RESULTS + 1)
    with pytest.raises(ValueError, match="at least 2"):
        await tools.search_exercise_templates(" ", limit=1)


async def test_missing_routine_and_workout_are_safe_errors() -> None:
    tools, _, _ = make_tools()
    server = create_mcp_server(tools)

    async with Client(server) as client:
        routine = await client.call_tool("get_training_routine", {"routine_id": "missing"})
        workout = await client.call_tool("get_workout", {"workout_id": "missing"})

    assert routine.is_error
    assert workout.is_error
    assert "not found" in str(routine.content).lower()
    assert "not found" in str(workout.content).lower()


async def test_hevy_not_configured_does_not_construct_client() -> None:
    tools, _, client = make_tools()

    result = await tools.get_hevy_connection_status()

    assert result.status == "not_configured"
    assert result.configured is False
    assert client.calls == 0


async def test_external_error_is_sanitized_and_secret_is_absent() -> None:
    secret = "sk-private-value-that-must-not-appear"
    client = FakeHevyClient(HevyHTTPError(401, f"rejected {secret}"))
    tools, _, _ = make_tools(api_key=secret, client=client)

    result = await tools.get_hevy_connection_status()
    serialized = result.model_dump_json()

    assert result.status == "unavailable"
    assert secret not in serialized
    assert "rejected" in result.detail.lower()


def test_public_contracts_are_strict_and_do_not_expose_internal_ids() -> None:
    schema = SystemStatus.model_json_schema()
    athlete_schema = AthleteSummary.model_json_schema()

    assert schema["additionalProperties"] is False
    assert athlete_schema["additionalProperties"] is False
    assert "id" not in AthleteSummary.model_fields
    assert "api_key" not in str(schema).lower()
