import asyncio
from collections.abc import Awaitable

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from sqlalchemy.ext.asyncio import AsyncEngine

from gym_coach.config import Settings, get_settings
from gym_coach.db import create_engine, create_session_factory
from gym_coach.integrations.hevy.client import HevyClient
from gym_coach.mcp.errors import GymCoachMCPError, InternalToolError
from gym_coach.mcp.instructions import MCP_INSTRUCTIONS
from gym_coach.mcp.repository import PostgresMCPRepository
from gym_coach.mcp.schemas import (
    AthleteSummary,
    ExerciseTemplateSearchResults,
    HevyConnectionStatus,
    RecentWorkouts,
    RoutineList,
    SystemStatus,
    TrainingRoutine,
    TrainingWorkout,
)
from gym_coach.mcp.tools import MCPTools

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True)


def create_mcp_server(tools: MCPTools) -> MCPServer[None]:
    server: MCPServer[None] = MCPServer(
        name="gym-coach",
        title="gym-coach training backend",
        description="Read-only access to normalized training data and backend status.",
        instructions=MCP_INSTRUCTIONS,
        version="0.1.0",
    )

    @server.tool(annotations=READ_ONLY)
    async def get_system_status() -> SystemStatus:
        """Return sanitized backend, Hevy, and PostgreSQL availability."""
        return await _safe(tools.get_system_status())

    @server.tool(annotations=READ_ONLY)
    async def get_hevy_connection_status() -> HevyConnectionStatus:
        """Check Hevy configuration and accessibility without exposing credentials."""
        return await _safe(tools.get_hevy_connection_status())

    @server.tool(annotations=READ_ONLY)
    async def get_athlete_summary() -> AthleteSummary:
        """Return the minimal structured athlete profile and active goals."""
        return await _safe(tools.get_athlete_summary())

    @server.tool(annotations=READ_ONLY)
    async def list_training_routines() -> RoutineList:
        """List active synchronized routines in stable backend order."""
        return await _safe(tools.list_training_routines())

    @server.tool(annotations=READ_ONLY)
    async def get_training_routine(routine_id: str) -> TrainingRoutine:
        """Return one active routine with planned exercises and sets."""
        return await _safe(tools.get_training_routine(routine_id))

    @server.tool(annotations=READ_ONLY)
    async def get_recent_workouts(limit: int = 10) -> RecentWorkouts:
        """Return at most 50 recent normalized workout summaries."""
        return await _safe(tools.get_recent_workouts(limit))

    @server.tool(annotations=READ_ONLY)
    async def get_workout(workout_id: str) -> TrainingWorkout:
        """Return one workout with completed exercises, sets, RPE, and notes."""
        return await _safe(tools.get_workout(workout_id))

    @server.tool(annotations=READ_ONLY)
    async def search_exercise_templates(
        query: str, limit: int = 10
    ) -> ExerciseTemplateSearchResults:
        """Search exercise templates by name and return at most 25 matches."""
        return await _safe(tools.search_exercise_templates(query, limit))

    return server


def build_mcp_tools(settings: Settings) -> tuple[MCPTools, AsyncEngine]:
    engine = create_engine(settings.database_url)

    def hevy_client_factory() -> HevyClient:
        if settings.hevy_api_key is None:
            raise RuntimeError("Hevy client requested without configuration")
        return HevyClient(
            settings.hevy_api_key,
            base_url=settings.hevy_base_url,
            timeout_seconds=settings.hevy_timeout_seconds,
            retry_attempts=settings.hevy_retry_attempts,
            retry_backoff_seconds=settings.hevy_retry_backoff_seconds,
        )

    repository = PostgresMCPRepository(create_session_factory(engine))
    return MCPTools(settings, repository, hevy_client_factory), engine


def run_stdio_server(settings: Settings | None = None) -> None:
    tools, engine = build_mcp_tools(settings or get_settings())
    try:
        create_mcp_server(tools).run("stdio")
    finally:
        asyncio.run(engine.dispose())


async def _safe[ResultT](awaitable: Awaitable[ResultT]) -> ResultT:
    try:
        return await awaitable
    except (GymCoachMCPError, ValueError):
        raise
    except Exception as exc:
        raise InternalToolError() from exc
