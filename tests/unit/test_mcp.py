from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID, uuid4

import pytest
from mcp import Client
from pydantic import SecretStr, ValidationError

from gym_coach.config import Settings
from gym_coach.integrations.hevy.errors import HevyHTTPError, HevyInvalidResponseError
from gym_coach.integrations.hevy.schemas import Routine, RoutineWriteRequest, UserInfo
from gym_coach.mcp.errors import ResourceNotFoundError
from gym_coach.mcp.repository import _to_coach_proposal
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
    ProposedPlanSet,
    RecentWorkouts,
    RoutineApplicationCommand,
    RoutineApplicationPreview,
    RoutineApplicationReconciliationContext,
    RoutineList,
    SystemStatus,
    TrainingGoalUpdate,
    TrainingPlanComparison,
    TrainingPlanProposal,
    TrainingPlanProposalInput,
    TrainingRoutine,
    TrainingWorkout,
    VerifiedPlanEvidence,
    WorkoutReviewAcknowledgement,
    WorkoutSummary,
)
from gym_coach.mcp.server import create_mcp_server
from gym_coach.mcp.tools import (
    MAX_EXERCISE_RESULTS,
    MAX_RECENT_WORKOUTS,
    MCPTools,
    _routine_request,
)
from gym_coach.metrics.service import ExerciseReport
from gym_coach.metrics.types import (
    AdherenceMetric,
    ExerciseProgress,
    MetricsSummary,
    StagnationResult,
)
from gym_coach.sync.hevy import HevySyncError
from gym_coach.sync.types import SyncCounts, SyncResult


class FakeRepository:
    def __init__(self) -> None:
        self.search_arguments: tuple[str, int] | None = None
        self.application_finished: tuple[str, list[str]] | None = None
        self.application_error_type: str | None = None
        self.application_action: Literal["create", "update"] = "create"
        self.reconciliation_context: RoutineApplicationReconciliationContext | None = None
        self.reconciled: tuple[str, list[str], str | None] | None = None

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
        self, data: TrainingPlanProposalInput, evidence: list[VerifiedPlanEvidence]
    ) -> TrainingPlanProposal | None:
        assert evidence
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
                title="Draft",
                workout_count=1,
                required_workout_count=1,
                optional_workout_count=0,
                exercise_count=1,
                set_count=1,
            ),
            rationale="Test rationale",
            exercise_changes=[],
            muscle_group_changes=[],
            unmatched_current_titles=[],
            unmatched_proposed_titles=[],
        )

    async def decide_plan_proposal(
        self, proposal_id: UUID, decision: Literal["approved", "rejected"]
    ) -> PlanDecisionResult | None:
        return PlanDecisionResult(
            proposal_id=proposal_id,
            status=decision,
            message="Decision recorded without modifying Hevy.",
        )

    async def acknowledge_workout_review(
        self, review_id: UUID
    ) -> WorkoutReviewAcknowledgement | None:
        return WorkoutReviewAcknowledgement(
            review_id=review_id,
            workout_external_id="workout-public-id",
        )

    async def prepare_routine_application(
        self, proposal_id: UUID
    ) -> RoutineApplicationPreview | None:
        return RoutineApplicationPreview(
            application_id=UUID("00000000-0000-0000-0000-000000000002"),
            proposal_id=proposal_id,
            action=self.application_action,
            routine_titles=["Upper A"],
            confirmation_token="one-time-token",
            warning="Confirm exact external write.",
        )

    async def claim_routine_application(
        self, proposal_id: UUID, confirmation_token: str
    ) -> RoutineApplicationCommand | None:
        if confirmation_token != "one-time-token":
            raise ValueError("The confirmation token is invalid")
        return RoutineApplicationCommand(
            application_id=UUID("00000000-0000-0000-0000-000000000002"),
            proposal_id=proposal_id,
            action=self.application_action,
            source_routine_id=("routine-source" if self.application_action == "update" else None),
            source_routine_hash=("stale-hash" if self.application_action == "update" else None),
            plan=_test_plan(self.application_action),
        )

    async def finish_routine_application(
        self,
        application_id: UUID,
        *,
        status: Literal["applied", "failed", "uncertain", "partial"],
        routine_ids: list[str],
        error_type: str | None,
    ) -> None:
        del application_id
        self.application_finished = (status, routine_ids)
        self.application_error_type = error_type

    async def get_routine_application_reconciliation_context(
        self, proposal_id: UUID
    ) -> RoutineApplicationReconciliationContext | None:
        del proposal_id
        return self.reconciliation_context

    async def reconcile_routine_application(
        self,
        application_id: UUID,
        *,
        status: Literal["applied", "partial", "uncertain"],
        routine_ids: list[str],
        error_type: str | None,
    ) -> None:
        del application_id
        self.reconciled = (status, routine_ids, error_type)


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


class FakeSyncRunner:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    async def sync(self) -> SyncResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return SyncResult(
            run_id="sync-run",
            counts=SyncCounts(inserted=1, updated=2, unchanged=3, deleted=4),
        )


class FakeHevyClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0
        self.update_calls = 0
        self.routines: list[Routine] = []
        self.reconciliation_routine: Routine | None = None
        self.get_routine_calls = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    async def get_user(self) -> UserInfo:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return UserInfo(id="not-exposed", name="Private Name", url=None)

    async def create_routine(self, request: RoutineWriteRequest) -> Routine:
        if self.error is not None:
            raise self.error
        return Routine(id="created-routine", title=request.routine.title, exercises=[])

    async def get_routine(self, routine_id: str) -> Routine:
        self.get_routine_calls += 1
        if self.reconciliation_routine is not None:
            return self.reconciliation_routine
        return Routine(id=routine_id, title="Existing", exercises=[])

    async def get_all_routines(self) -> list[Routine]:
        return self.routines

    async def update_routine(self, routine_id: str, request: RoutineWriteRequest) -> Routine:
        self.update_calls += 1
        if self.error is not None:
            raise self.error
        return Routine(id=routine_id, title=request.routine.title, exercises=[])


def _test_plan(action: Literal["create", "update"] = "create") -> TrainingPlanProposalInput:
    evidence_id = f"metrics:summary:28d:{datetime.now(UTC).date().isoformat()}"
    return TrainingPlanProposalInput(
        kind="new_routine" if action == "create" else "routine_update",
        title="Plan",
        summary="Summary",
        rationale="Rationale",
        evidence_ids=[evidence_id],
        changes=[{"description": "Change", "evidence_ids": [evidence_id]}],
        source_routine_id="routine-source" if action == "update" else None,
        workouts=[
            {
                "title": "Upper A",
                "exercises": [
                    {
                        "exercise_template_external_id": "template-public-id",
                        "title": "Bench",
                        "rest_seconds": 120,
                        "sets": [{"reps_min": 8, "reps_max": 12}],
                    }
                ],
            }
        ],
    )


def make_tools(
    *,
    api_key: str | None = None,
    client: FakeHevyClient | None = None,
    sync_runner: FakeSyncRunner | None = None,
) -> tuple[MCPTools, FakeRepository, FakeHevyClient]:
    repository = FakeRepository()
    fake_client = client or FakeHevyClient()
    settings = Settings(
        _env_file=None,
        HEVY_API_KEY=SecretStr(api_key) if api_key is not None else None,
    )
    tools = MCPTools(
        settings,
        repository,
        FakeMetrics(),
        lambda: fake_client,
        (lambda: sync_runner) if sync_runner is not None else None,
    )
    return tools, repository, fake_client


async def test_server_initializes_and_enumerates_expected_tools() -> None:
    tools, _, _ = make_tools()
    server = create_mcp_server(tools)

    registered = await server.list_tools()

    assert {tool.name for tool in registered} == {
        "get_system_status",
        "search_nutrition_catalogue",
        "save_nutrition_food",
        "save_nutrition_recipe",
        "preview_nutrition_meal",
        "log_nutrition_meal",
        "void_nutrition_meal",
        "get_daily_nutrition",
        "preview_nutrition_target",
        "save_confirmed_nutrition_target",
        "get_nutrition_day_review",
        "confirm_nutrition_day",
        "get_weekly_coaching_review",
        "compare_workout_to_current_routine",
        "get_workout_coaching_review",
        "get_hevy_connection_status",
        "sync_hevy",
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
        "acknowledge_automatic_workout_review",
        "get_training_history_assessment",
        "get_coaching_assessment",
        "save_confirmed_athlete_measurement",
        "save_confirmed_athlete_check_in",
        "preview_training_plan_application",
        "apply_training_plan_to_hevy",
        "reconcile_training_plan_application",
    }
    annotations = {tool.name: tool.annotations for tool in registered}
    assert annotations["get_training_metrics"].read_only_hint is True
    assert annotations["save_confirmed_athlete_profile"].read_only_hint is False


async def test_automatic_review_acknowledgement_is_local_and_idempotent_boundary() -> None:
    tools, _, _ = make_tools()
    review_id = uuid4()

    result = await tools.acknowledge_automatic_workout_review(review_id)

    assert result.review_id == review_id
    assert result.status == "completed"


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
        limitations_reviewed=True,
        preferences_reviewed=True,
        lifestyle_reviewed=True,
        nutrition_reviewed=True,
        health_reviewed=True,
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
    evidence_id = f"metrics:summary:28d:{datetime.now(UTC).date().isoformat()}"
    plan = TrainingPlanProposalInput(
        kind="new_routine",
        title="Four-day plan",
        summary="A balanced draft",
        rationale="Matches the confirmed availability and goal",
        evidence_ids=[evidence_id],
        changes=[
            {
                "description": "Distribute training across the week",
                "evidence_ids": [evidence_id],
            }
        ],
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

    payload = plan.model_dump(mode="json")
    payload["changes"] = []
    with pytest.raises(ValueError, match="justify at least one change"):
        await tools.create_training_plan_proposal(
            TrainingPlanProposalInput.model_validate(payload), user_requested=True
        )

    stale_date = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    stale_id = f"metrics:summary:28d:{stale_date}"
    payload["evidence_ids"] = [stale_id]
    payload["changes"] = [{"description": "Stale evidence", "evidence_ids": [stale_id]}]
    with pytest.raises(ValueError, match="stale"):
        await tools.create_training_plan_proposal(
            TrainingPlanProposalInput.model_validate(payload), user_requested=True
        )

    unknown_id = "metrics:unknown"
    payload["evidence_ids"] = [unknown_id]
    payload["changes"] = [{"description": "Unknown evidence", "evidence_ids": [unknown_id]}]
    with pytest.raises(ValueError, match="unknown or unverifiable"):
        await tools.create_training_plan_proposal(
            TrainingPlanProposalInput.model_validate(payload), user_requested=True
        )


def test_plan_sets_support_exactly_one_prescription_dimension() -> None:
    duration = ProposedPlanSet(duration_seconds_min=30, duration_seconds_max=60)
    distance = ProposedPlanSet(
        distance_meters_min=Decimal("500"), distance_meters_max=Decimal("1000")
    )

    assert duration.duration_seconds_max == 60
    assert distance.distance_meters_min == Decimal("500")
    weighted = ProposedPlanSet(weight_kg=Decimal("42.5"), reps_min=8, reps_max=10)
    assert weighted.weight_kg == Decimal("42.5")
    with pytest.raises(ValidationError, match="exactly one"):
        ProposedPlanSet(reps_min=8, reps_max=10, duration_seconds_min=30, duration_seconds_max=60)
    with pytest.raises(ValidationError, match="provided together"):
        ProposedPlanSet(duration_seconds_min=30)


def test_mcp_profile_requires_explicit_safety_and_preference_review() -> None:
    with pytest.raises(ValidationError):
        AthleteProfileUpdate(
            experience_level="intermediate",
            training_days_per_week=3,
        )


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


async def test_hevy_application_requires_preview_and_second_confirmation() -> None:
    tools, repository, _ = make_tools(api_key="configured-placeholder")
    proposal_id = uuid4()

    preview = await tools.preview_training_plan_application(proposal_id)
    with pytest.raises(ValueError, match="Explicit athlete confirmation"):
        await tools.apply_training_plan_to_hevy(
            proposal_id,
            preview.confirmation_token,
            user_confirmed=False,
        )
    with pytest.raises(ValueError, match="token is invalid"):
        await tools.apply_training_plan_to_hevy(
            proposal_id,
            "wrong-token",
            user_confirmed=True,
        )

    applied = await tools.apply_training_plan_to_hevy(
        proposal_id,
        preview.confirmation_token,
        user_confirmed=True,
    )

    assert applied.status == "applied"
    assert applied.routine_ids == ["created-routine"]
    assert repository.application_finished == ("applied", ["created-routine"])


async def test_hevy_application_synchronizes_postgres_after_confirmed_write() -> None:
    sync_runner = FakeSyncRunner()
    tools, _, _ = make_tools(api_key="configured-placeholder", sync_runner=sync_runner)
    proposal_id = uuid4()
    preview = await tools.preview_training_plan_application(proposal_id)

    result = await tools.apply_training_plan_to_hevy(
        proposal_id,
        preview.confirmation_token,
        user_confirmed=True,
    )

    assert result.status == "applied"
    assert result.sync_status == "succeeded"
    assert sync_runner.calls == 1


async def test_manual_hevy_sync_requires_confirmation_and_returns_counts() -> None:
    sync_runner = FakeSyncRunner()
    tools, _, _ = make_tools(api_key="configured-placeholder", sync_runner=sync_runner)

    with pytest.raises(ValueError, match="Explicit athlete confirmation"):
        await tools.sync_hevy(user_confirmed=False)

    result = await tools.sync_hevy(user_confirmed=True)

    assert result.status == "succeeded"
    assert result.run_id == "sync-run"
    assert result.inserted == 1
    assert result.updated == 2
    assert result.unchanged == 3
    assert result.deleted == 4
    assert sync_runner.calls == 1


async def test_hevy_application_keeps_write_result_when_postgres_sync_fails() -> None:
    sync_runner = FakeSyncRunner(HevySyncError("sync unavailable"))
    tools, _, _ = make_tools(api_key="configured-placeholder", sync_runner=sync_runner)
    proposal_id = uuid4()
    preview = await tools.preview_training_plan_application(proposal_id)

    result = await tools.apply_training_plan_to_hevy(
        proposal_id,
        preview.confirmation_token,
        user_confirmed=True,
    )

    assert result.status == "applied"
    assert result.sync_status == "failed"
    assert "synchronization failed" in result.message


async def test_hevy_update_refuses_a_remote_routine_changed_after_preview() -> None:
    client = FakeHevyClient()
    tools, repository, _ = make_tools(api_key="configured-placeholder", client=client)
    repository.application_action = "update"
    proposal_id = uuid4()
    preview = await tools.preview_training_plan_application(proposal_id)

    result = await tools.apply_training_plan_to_hevy(
        proposal_id,
        preview.confirmation_token,
        user_confirmed=True,
    )

    assert result.status == "failed"
    assert client.update_calls == 0
    assert repository.application_finished == ("failed", [])
    assert result.error_code == "stale_routine"


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (HevyHTTPError(403, "private provider detail"), "failed", "hevy_http_403"),
        (
            HevyInvalidResponseError("private provider payload"),
            "uncertain",
            "hevy_invalid_response",
        ),
    ],
)
async def test_hevy_write_failure_returns_safe_actionable_diagnostic(
    error: Exception,
    expected_status: str,
    expected_code: str,
) -> None:
    client = FakeHevyClient(error)
    tools, repository, _ = make_tools(api_key="configured-placeholder", client=client)
    proposal_id = uuid4()
    preview = await tools.preview_training_plan_application(proposal_id)

    result = await tools.apply_training_plan_to_hevy(
        proposal_id,
        preview.confirmation_token,
        user_confirmed=True,
    )

    assert result.status == expected_status
    assert result.error_code == expected_code
    assert expected_code in result.message
    assert "private provider" not in result.model_dump_json()
    assert repository.application_error_type == expected_code


async def test_reconcile_create_records_only_exact_remote_matches() -> None:
    client = FakeHevyClient()
    tools, repository, _ = make_tools(api_key="configured-placeholder", client=client)
    proposal_id = uuid4()
    plan_data = _test_plan().model_dump(mode="json")
    second = {**plan_data["workouts"][0], "title": "Lower A"}
    plan_data["workouts"].append(second)
    plan = TrainingPlanProposalInput.model_validate(plan_data)
    repository.reconciliation_context = RoutineApplicationReconciliationContext(
        application_id=UUID("00000000-0000-0000-0000-000000000002"),
        proposal_id=proposal_id,
        action="create",
        status="uncertain",
        applied_at=datetime.now(UTC),
        recorded_routine_ids=[],
        plan=plan,
    )
    client.routines = [
        Routine.model_validate(
            {
                "id": "created-upper",
                "title": "Upper A",
                "folder_id": None,
                "created_at": datetime.now(UTC),
                "exercises": [
                    {
                        "title": "Bench",
                        "exercise_template_id": "template-public-id",
                        "rest_seconds": 120,
                        "sets": [
                            {
                                "type": "normal",
                                "rep_range": {"start": 8, "end": 12},
                            }
                        ],
                    }
                ],
            }
        )
    ]

    result = await tools.reconcile_training_plan_application(proposal_id, user_confirmed=True)

    assert result.status == "partial"
    assert result.matched_workout_indexes == [0]
    assert result.routine_ids == ["created-upper"]
    assert repository.reconciled == (
        "partial",
        ["created-upper"],
        "reconciled_partial",
    )


async def test_reconcile_update_reads_source_and_matches_exact_plan() -> None:
    client = FakeHevyClient()
    sync_runner = FakeSyncRunner()
    tools, repository, _ = make_tools(
        api_key="configured-placeholder", client=client, sync_runner=sync_runner
    )
    proposal_id = uuid4()
    plan = _test_plan("update")
    client.reconciliation_routine = Routine.model_validate(
        {
            "id": "routine-source",
            "title": "Upper A",
            "folder_id": None,
            "exercises": [
                {
                    "title": "Bench",
                    "exercise_template_id": "template-public-id",
                    "rest_seconds": 120,
                    "sets": [{"type": "normal", "rep_range": {"start": 8, "end": 12}}],
                }
            ],
        }
    )
    repository.reconciliation_context = RoutineApplicationReconciliationContext(
        application_id=UUID("00000000-0000-0000-0000-000000000002"),
        proposal_id=proposal_id,
        action="update",
        status="uncertain",
        applied_at=datetime.now(UTC),
        recorded_routine_ids=[],
        plan=plan,
    )

    result = await tools.reconcile_training_plan_application(proposal_id, user_confirmed=True)

    assert result.status == "applied"
    assert result.matched_workout_indexes == [0]
    assert result.routine_ids == ["routine-source"]
    assert result.sync_status == "succeeded"
    assert sync_runner.calls == 1
    assert client.get_routine_calls == 1
    assert repository.reconciled == ("applied", ["routine-source"], None)


def test_routine_request_assigns_shared_hevy_superset_ids() -> None:
    plan = {
        "title": "Upper paired",
        "exercises": [
            {
                "title": "Press",
                "exercise_template_external_id": "template-press",
                "rest_seconds": 60,
                "superset_group": "push_pull",
                "sets": [{"reps_min": 8, "reps_max": 12}],
            },
            {
                "title": "Row",
                "exercise_template_external_id": "template-row",
                "rest_seconds": 60,
                "superset_group": "push_pull",
                "sets": [{"reps_min": 8, "reps_max": 12}],
            },
            {
                "title": "Curl",
                "exercise_template_external_id": "template-curl",
                "rest_seconds": 60,
                "sets": [{"reps_min": 10, "reps_max": 15}],
            },
        ],
    }

    request = _routine_request(plan)

    assert [item.superset_id for item in request.routine.exercises] == [1, 1, None]


def test_routine_request_preserves_prescribed_weight() -> None:
    request = _routine_request(
        {
            "title": "Weighted upper",
            "exercises": [
                {
                    "title": "Press",
                    "exercise_template_external_id": "template-press",
                    "rest_seconds": 120,
                    "sets": [{"weight_kg": "42.5", "reps_min": 8, "reps_max": 10}],
                }
            ],
        }
    )

    assert request.routine.exercises[0].sets[0].weight_kg == 42.5


def test_public_plan_conversion_preserves_prescribed_weight() -> None:
    public_plan = TrainingPlanProposalInput(
        kind="new_routine",
        title="Weighted upper",
        summary="A plan with an evidenced load.",
        rationale="The recent training history supports this starting load.",
        evidence_ids=["history:bench"],
        workouts=[
            {
                "title": "Upper",
                "exercises": [
                    {
                        "title": "Press",
                        "exercise_template_external_id": "template-press",
                        "rest_seconds": 120,
                        "sets": [{"weight_kg": "42.5", "reps_min": 8, "reps_max": 10}],
                    }
                ],
            }
        ],
    )

    internal = _to_coach_proposal(public_plan)

    assert internal.workouts[0].exercises[0].sets[0].weight_kg == Decimal("42.5")


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
