import asyncio
from collections.abc import Awaitable
from typing import Literal
from uuid import UUID

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from sqlalchemy.ext.asyncio import AsyncEngine

from gym_coach.config import Settings, get_settings
from gym_coach.db import create_engine, create_session_factory
from gym_coach.integrations.hevy.client import HevyClient
from gym_coach.integrations.hevy.raw_store import RawResponseStore
from gym_coach.mcp.errors import GymCoachMCPError, InternalToolError
from gym_coach.mcp.instructions import MCP_INSTRUCTIONS
from gym_coach.mcp.repository import PostgresMCPRepository
from gym_coach.mcp.schemas import (
    AthleteCheckInInput,
    AthleteCheckInView,
    AthleteMeasurementInput,
    AthleteMeasurementView,
    AthleteProfileUpdate,
    AthleteSummary,
    CoachingAssessment,
    ExerciseProgressReport,
    ExerciseTemplateSearchResults,
    GoalMutationResult,
    HevyConnectionStatus,
    HevySyncResult,
    OnboardingStatus,
    PlanDecisionResult,
    ProfileMutationResult,
    RecentWorkouts,
    RoutineApplicationPreview,
    RoutineApplicationReconciliationResult,
    RoutineApplicationResult,
    RoutineList,
    SystemStatus,
    TrainingGoalUpdate,
    TrainingHistoryAssessment,
    TrainingMetrics,
    TrainingPlanComparison,
    TrainingPlanProposal,
    TrainingPlanProposalInput,
    TrainingRoutine,
    TrainingWorkout,
    WorkoutReviewAcknowledgement,
)
from gym_coach.mcp.tools import MCPTools
from gym_coach.metrics.service import MetricsService
from gym_coach.sync.hevy import HevySyncService

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True)
WRITE_LOCAL = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False)
SYNC_LOCAL = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True)
WRITE_HEVY = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False)


def create_mcp_server(tools: MCPTools) -> MCPServer[None]:
    server: MCPServer[None] = MCPServer(
        name="gym-coach",
        title="gym-coach training backend",
        description="Controlled access to normalized training data and confirmed local state.",
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

    @server.tool(annotations=SYNC_LOCAL)
    async def sync_hevy(user_confirmed: Literal[True]) -> HevySyncResult:
        """Synchronize a complete Hevy snapshot into PostgreSQL after explicit confirmation."""
        return await _safe(tools.sync_hevy(user_confirmed=user_confirmed))

    @server.tool(annotations=READ_ONLY)
    async def get_athlete_summary() -> AthleteSummary:
        """Return the minimal structured athlete profile and active goals."""
        return await _safe(tools.get_athlete_summary())

    @server.tool(annotations=READ_ONLY)
    async def get_onboarding_status() -> OnboardingStatus:
        """Return missing profile fields and the next safe onboarding action."""
        return await _safe(tools.get_onboarding_status())

    @server.tool(annotations=READ_ONLY)
    async def get_training_history_assessment() -> TrainingHistoryAssessment:
        """Infer training-history depth from normalized workouts, with confidence and limits."""
        return await _safe(tools.get_training_history_assessment())

    @server.tool(annotations=READ_ONLY)
    async def get_coaching_assessment() -> CoachingAssessment:
        """Return deterministic interview gaps, history, nutrition ranges, and sourced rules."""
        return await _safe(tools.get_coaching_assessment())

    @server.tool(annotations=WRITE_LOCAL)
    async def save_confirmed_athlete_profile(
        profile: AthleteProfileUpdate, user_confirmed: Literal[True]
    ) -> ProfileMutationResult:
        """Save a profile after explicit safety/preference review and summary confirmation."""
        return await _safe(
            tools.save_confirmed_athlete_profile(profile, user_confirmed=user_confirmed)
        )

    @server.tool(annotations=WRITE_LOCAL)
    async def save_confirmed_athlete_measurement(
        measurement: AthleteMeasurementInput, user_confirmed: Literal[True]
    ) -> AthleteMeasurementView:
        """Store a dated measurement only after the athlete confirms the exact values."""
        return await _safe(
            tools.save_confirmed_athlete_measurement(measurement, user_confirmed=user_confirmed)
        )

    @server.tool(annotations=WRITE_LOCAL)
    async def save_confirmed_athlete_check_in(
        check_in: AthleteCheckInInput, user_confirmed: Literal[True]
    ) -> AthleteCheckInView:
        """Store a dated wellbeing and adherence check-in after explicit confirmation."""
        return await _safe(
            tools.save_confirmed_athlete_check_in(check_in, user_confirmed=user_confirmed)
        )

    @server.tool(annotations=WRITE_LOCAL)
    async def add_confirmed_training_goal(
        goal: TrainingGoalUpdate, user_confirmed: Literal[True]
    ) -> GoalMutationResult:
        """Add a versioned goal only after the athlete confirms its structured summary."""
        return await _safe(tools.add_confirmed_training_goal(goal, user_confirmed=user_confirmed))

    @server.tool(annotations=WRITE_LOCAL)
    async def revise_confirmed_training_goal(
        goal_version: int,
        goal: TrainingGoalUpdate,
        user_confirmed: Literal[True],
    ) -> GoalMutationResult:
        """Archive and supersede one active goal after explicit athlete confirmation."""
        return await _safe(
            tools.revise_confirmed_training_goal(goal_version, goal, user_confirmed=user_confirmed)
        )

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

    @server.tool(annotations=READ_ONLY)
    async def get_training_metrics(window_days: int = 28) -> TrainingMetrics:
        """Return deterministic volume, repetitions, adherence, and stagnation metrics."""
        return await _safe(tools.get_training_metrics(window_days))

    @server.tool(annotations=READ_ONLY)
    async def get_exercise_progress(
        exercise_template_id: str, window_days: int = 180
    ) -> ExerciseProgressReport:
        """Return deterministic e1RM progression and stagnation for one exercise."""
        return await _safe(tools.get_exercise_progress(exercise_template_id, window_days))

    @server.tool(annotations=WRITE_LOCAL)
    async def create_training_plan_proposal(
        plan: TrainingPlanProposalInput, user_requested: Literal[True]
    ) -> TrainingPlanProposal:
        """Store a requested local draft whose individual changes cite verified evidence."""
        return await _safe(tools.create_training_plan_proposal(plan, user_requested=user_requested))

    @server.tool(annotations=READ_ONLY)
    async def get_training_plan_proposal(proposal_id: UUID) -> TrainingPlanProposal:
        """Return a stored local training plan proposal and its decision status."""
        return await _safe(tools.get_training_plan_proposal(proposal_id))

    @server.tool(annotations=READ_ONLY)
    async def compare_training_plan_proposal(proposal_id: UUID) -> TrainingPlanComparison:
        """Compare workouts, exercises, sets, and muscle groups without applying changes."""
        return await _safe(tools.compare_training_plan_proposal(proposal_id))

    @server.tool(annotations=WRITE_LOCAL)
    async def decide_training_plan_proposal(
        proposal_id: UUID,
        decision: Literal["approved", "rejected"],
        user_confirmed: Literal[True],
    ) -> PlanDecisionResult:
        """Record a confirmed local decision; never apply the proposal to Hevy."""
        return await _safe(
            tools.decide_training_plan_proposal(
                proposal_id, decision, user_confirmed=user_confirmed
            )
        )

    @server.tool(annotations=WRITE_LOCAL)
    async def preview_training_plan_application(
        proposal_id: UUID,
    ) -> RoutineApplicationPreview:
        """Prepare an exact approved Hevy write and issue a one-time confirmation token."""
        return await _safe(tools.preview_training_plan_application(proposal_id))

    @server.tool(annotations=WRITE_HEVY)
    async def apply_training_plan_to_hevy(
        proposal_id: UUID,
        confirmation_token: str,
        user_confirmed: Literal[True],
    ) -> RoutineApplicationResult:
        """Apply the previewed plan and automatically sync PostgreSQL from Hevy."""
        return await _safe(
            tools.apply_training_plan_to_hevy(
                proposal_id,
                confirmation_token,
                user_confirmed=user_confirmed,
            )
        )

    @server.tool(annotations=WRITE_LOCAL)
    async def reconcile_training_plan_application(
        proposal_id: UUID,
        user_confirmed: Literal[True],
    ) -> RoutineApplicationReconciliationResult:
        """Compare an uncertain attempt with live Hevy and sync PostgreSQL if confirmed."""
        return await _safe(
            tools.reconcile_training_plan_application(proposal_id, user_confirmed=user_confirmed)
        )

    @server.tool(annotations=WRITE_LOCAL)
    async def acknowledge_automatic_workout_review(
        review_id: UUID,
    ) -> WorkoutReviewAcknowledgement:
        """Mark a claimed automatic review complete after its Telegram brief is prepared."""
        return await _safe(tools.acknowledge_automatic_workout_review(review_id))

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
            raw_store=RawResponseStore(settings.raw_data_dir),
        )

    session_factory = create_session_factory(engine)
    repository = PostgresMCPRepository(session_factory)

    def hevy_sync_factory() -> HevySyncService:
        return HevySyncService(hevy_client_factory(), session_factory)

    return MCPTools(
        settings,
        repository,
        MetricsService(session_factory),
        hevy_client_factory,
        hevy_sync_factory,
    ), engine


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
