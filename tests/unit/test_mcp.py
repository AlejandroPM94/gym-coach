from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID, uuid4

import pytest
from mcp import Client
from pydantic import SecretStr

from gym_coach.config import Settings
from gym_coach.integrations.hevy.errors import HevyHTTPError
from gym_coach.integrations.hevy.schemas import UserInfo
from gym_coach.mcp.errors import ResourceNotFoundError
from gym_coach.mcp.schemas import (
    AthleteProfileUpdate,
    AthleteSummary,
    ExerciseTemplateSearchResults,
    ExerciseTemplateSummary,
    GoalMutationResult,
    OnboardingStatus,
    PlanComparisonSide,
    PlanDecisionResult,
    ProfileMutationResult,
    RecentWorkouts,
    RoutineList,
    SystemStatus,
    TrainingGoalUpdate,
    TrainingPlanComparison,
    TrainingPlanProposal,
    TrainingPlanProposalInput,
    TrainingRoutine,
    TrainingWorkout,
    WorkoutSummary,
)
from gym_coach.mcp.server import create_mcp_server
from gym_coach.mcp.tools import MAX_EXERCISE_RESULTS, MAX_RECENT_WORKOUTS, MCPTools
from gym_coach.metrics.service import ExerciseReport
from gym_coach.metrics.types import (
    AdherenceMetric,
    ExerciseProgress,
    MetricsSummary,
    StagnationResult,
)


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
            training_days_per_week=4,
            pending_fields=["goals"],
        )

    async def onboarding_status(self) -> OnboardingStatus:
        return OnboardingStatus(
            profile_present=False,
            active_goal_count=0,
            pending_fields=["experience_level", "goals"],
            ready_for_training_analysis=False,
            next_action="Ask for missing fields and confirmation.",
        )

    async def save_profile(self, data: AthleteProfileUpdate) -> ProfileMutationResult:
        del data
        return ProfileMutationResult(
            profile_version=1,
            message="Confirmed athlete profile saved in PostgreSQL.",
        )

    async def add_goal(self, data: TrainingGoalUpdate) -> GoalMutationResult | None:
        del data
        return GoalMutationResult(goal_version=1, message="Confirmed goal saved.")

    async def revise_goal(
        self, goal_version: int, data: TrainingGoalUpdate
    ) -> GoalMutationResult | None:
        del goal_version, data
        return GoalMutationResult(goal_version=2, message="Confirmed goal revised.")

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

    async def exercise_template_exists(self, external_id: str) -> bool:
        return external_id == "template-public-id"

    async def create_plan_proposal(
        self, data: TrainingPlanProposalInput
    ) -> TrainingPlanProposal | None:
        return TrainingPlanProposal(
            proposal_id=uuid4(),
            status="draft",
            created_at=datetime.now(UTC),
            plan=data,
        )

    async def get_plan_proposal(self, proposal_id: UUID) -> TrainingPlanProposal | None:
        del proposal_id
        return None

    async def compare_plan_proposal(self, proposal_id: UUID) -> TrainingPlanComparison | None:
        return TrainingPlanComparison(
            proposal_id=proposal_id,
            status="draft",
            proposed=PlanComparisonSide(
                title="Draft", workout_count=1, exercise_count=1, set_count=1
            ),
            rationale="Test rationale",
        )

    async def decide_plan_proposal(
        self, proposal_id: UUID, decision: Literal["approved", "rejected"]
    ) -> PlanDecisionResult | None:
        return PlanDecisionResult(
            proposal_id=proposal_id,
            status=decision,
            message="Decision recorded without modifying Hevy.",
        )


class FakeMetrics:
    async def summary(
        self,
        *,
        as_of: datetime,
        window_days: int,
        target_sessions_per_week: Decimal,
    ) -> MetricsSummary:
        del as_of
        return MetricsSummary(
            workouts=8,
            total_reps=240,
            total_volume_kg_reps=Decimal("12000.00"),
            adherence=AdherenceMetric(
                window_days=window_days,
                target_sessions_per_week=target_sessions_per_week,
                expected_sessions=Decimal("16"),
                completed_sessions=8,
                adherence_percent=Decimal("50.00"),
                matched_routine_sessions=8,
            ),
            stalled_exercises=(),
        )

    async def exercise_report(
        self,
        exercise_template_external_id: str,
        *,
        as_of: datetime,
        window_days: int,
    ) -> ExerciseReport:
        del as_of, window_days
        return ExerciseReport(
            progress=ExerciseProgress(
                exercise_template_external_id=exercise_template_external_id,
                sessions=(),
                latest_e1rm_kg=Decimal("100.00"),
                previous_e1rm_kg=Decimal("95.00"),
                e1rm_change_kg=Decimal("5.00"),
                e1rm_change_percent=Decimal("5.26"),
            ),
            stagnation=StagnationResult(
                exercise_template_external_id=exercise_template_external_id,
                is_stalled=False,
                reason="Progress is above the configured threshold.",
                qualifying_sessions=4,
                span_days=30,
                improvement_percent=Decimal("5.26"),
            ),
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
    tools = MCPTools(settings, repository, FakeMetrics(), lambda: fake_client)
    return tools, repository, fake_client


async def test_server_initializes_and_enumerates_expected_tools() -> None:
    tools, _, _ = make_tools()
    server = create_mcp_server(tools)

    registered = await server.list_tools()

    assert {tool.name for tool in registered} == {
        "get_system_status",
        "get_hevy_connection_status",
        "get_athlete_summary",
        "get_onboarding_status",
        "save_confirmed_athlete_profile",
        "add_confirmed_training_goal",
        "revise_confirmed_training_goal",
        "list_training_routines",
        "get_training_routine",
        "get_recent_workouts",
        "get_workout",
        "search_exercise_templates",
        "get_training_metrics",
        "get_exercise_progress",
        "create_training_plan_proposal",
        "get_training_plan_proposal",
        "compare_training_plan_proposal",
        "decide_training_plan_proposal",
    }
    annotations = {tool.name: tool.annotations for tool in registered}
    assert annotations["get_training_metrics"].read_only_hint is True
    assert annotations["save_confirmed_athlete_profile"].read_only_hint is False


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


async def test_profile_and_goal_writes_require_explicit_confirmation() -> None:
    tools, _, _ = make_tools()
    profile = AthleteProfileUpdate(
        experience_level="intermediate",
        training_days_per_week=4,
        session_duration_minutes=60,
        equipment=["full gym"],
    )
    goal = TrainingGoalUpdate(
        goal_type="hypertrophy",
        description="Build muscle with four sustainable weekly sessions",
    )

    with pytest.raises(ValueError, match="Explicit athlete confirmation"):
        await tools.save_confirmed_athlete_profile(profile, user_confirmed=False)
    with pytest.raises(ValueError, match="Explicit athlete confirmation"):
        await tools.add_confirmed_training_goal(goal, user_confirmed=False)

    saved_profile = await tools.save_confirmed_athlete_profile(profile, user_confirmed=True)
    saved_goal = await tools.add_confirmed_training_goal(goal, user_confirmed=True)

    assert saved_profile.user_confirmation_recorded is True
    assert saved_goal.user_confirmation_recorded is True


async def test_metrics_are_calculated_by_backend_and_bounded() -> None:
    tools, _, _ = make_tools()

    summary = await tools.get_training_metrics(28)
    progress = await tools.get_exercise_progress("template-public-id", 180)

    assert summary.total_volume_kg_reps == "12000.00"
    assert summary.evidence_id.startswith("metrics:summary:28d:")
    assert progress.latest_e1rm_kg == "100.00"
    assert progress.evidence_id.startswith("metrics:exercise:template-public-id:180d:")
    with pytest.raises(ValueError, match="between 7 and 365"):
        await tools.get_training_metrics(366)
    with pytest.raises(ValueError, match="between 30 and 730"):
        await tools.get_exercise_progress("template-public-id", 29)
    with pytest.raises(ResourceNotFoundError, match="not found"):
        await tools.get_exercise_progress("missing-template", 180)


async def test_plan_draft_requires_request_and_never_applies_to_hevy() -> None:
    tools, _, _ = make_tools()
    plan = TrainingPlanProposalInput(
        kind="new_routine",
        title="Four-day plan",
        summary="A balanced draft",
        rationale="Matches the confirmed availability and goal",
        evidence_ids=["metrics:summary:28d:2026-08-06"],
        workouts=[
            {
                "title": "Upper A",
                "exercises": [
                    {
                        "exercise_template_external_id": "template-public-id",
                        "title": "Barbell Bench Press",
                        "rest_seconds": 180,
                        "sets": [{"reps_min": 6, "reps_max": 8}],
                    }
                ],
            }
        ],
    )

    with pytest.raises(ValueError, match="explicitly request"):
        await tools.create_training_plan_proposal(plan, user_requested=False)

    proposal = await tools.create_training_plan_proposal(plan, user_requested=True)

    assert proposal.status == "draft"
    assert proposal.applied_to_hevy is False


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
