from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib.metadata import PackageNotFoundError, version
from typing import Literal, Protocol, Self
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from gym_coach.config import Settings
from gym_coach.integrations.hevy.errors import HevyError
from gym_coach.integrations.hevy.schemas import UserInfo
from gym_coach.mcp.errors import BackendUnavailableError, ResourceNotFoundError
from gym_coach.mcp.schemas import (
    AdherenceSummary,
    AthleteProfileUpdate,
    AthleteSummary,
    ComponentStatus,
    ExerciseProgressReport,
    ExerciseSessionSummary,
    ExerciseTemplateSearchResults,
    GoalMutationResult,
    HevyConnectionStatus,
    OnboardingStatus,
    PlanDecisionResult,
    ProfileMutationResult,
    RecentWorkouts,
    RoutineList,
    StagnationSummary,
    SystemStatus,
    TrainingGoalUpdate,
    TrainingMetrics,
    TrainingPlanComparison,
    TrainingPlanProposal,
    TrainingPlanProposalInput,
    TrainingRoutine,
    TrainingWorkout,
)
from gym_coach.metrics.service import ExerciseReport, MetricsError
from gym_coach.metrics.types import MetricsSummary, StagnationResult

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

    async def onboarding_status(self) -> OnboardingStatus: ...

    async def save_profile(self, data: AthleteProfileUpdate) -> ProfileMutationResult: ...

    async def add_goal(self, data: TrainingGoalUpdate) -> GoalMutationResult | None: ...

    async def revise_goal(
        self, goal_version: int, data: TrainingGoalUpdate
    ) -> GoalMutationResult | None: ...

    async def list_routines(self) -> RoutineList: ...

    async def get_routine(self, external_id: str) -> TrainingRoutine | None: ...

    async def recent_workouts(self, limit: int) -> RecentWorkouts: ...

    async def get_workout(self, external_id: str) -> TrainingWorkout | None: ...

    async def search_exercise_templates(
        self, query: str, limit: int
    ) -> ExerciseTemplateSearchResults: ...

    async def exercise_template_exists(self, external_id: str) -> bool: ...

    async def create_plan_proposal(
        self, data: TrainingPlanProposalInput
    ) -> TrainingPlanProposal | None: ...

    async def get_plan_proposal(self, proposal_id: UUID) -> TrainingPlanProposal | None: ...

    async def compare_plan_proposal(self, proposal_id: UUID) -> TrainingPlanComparison | None: ...

    async def decide_plan_proposal(
        self, proposal_id: UUID, decision: Literal["approved", "rejected"]
    ) -> PlanDecisionResult | None: ...


class MCPMetricsReader(Protocol):
    async def summary(
        self,
        *,
        as_of: datetime,
        window_days: int,
        target_sessions_per_week: Decimal,
    ) -> MetricsSummary: ...

    async def exercise_report(
        self,
        exercise_template_external_id: str,
        *,
        as_of: datetime,
        window_days: int,
    ) -> ExerciseReport: ...


class MCPTools:
    def __init__(
        self,
        settings: Settings,
        repository: MCPReadRepository,
        metrics: MCPMetricsReader,
        hevy_client_factory: HevyClientFactory,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._metrics = metrics
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

    async def get_onboarding_status(self) -> OnboardingStatus:
        return await self._database_call(self._repository.onboarding_status)

    async def save_confirmed_athlete_profile(
        self, profile: AthleteProfileUpdate, *, user_confirmed: bool
    ) -> ProfileMutationResult:
        _require_confirmation(user_confirmed)
        return await self._database_call(lambda: self._repository.save_profile(profile))

    async def add_confirmed_training_goal(
        self, goal: TrainingGoalUpdate, *, user_confirmed: bool
    ) -> GoalMutationResult:
        _require_confirmation(user_confirmed)
        result = await self._database_call(lambda: self._repository.add_goal(goal))
        if result is None:
            raise ResourceNotFoundError("Athlete profile must be configured before adding goals")
        return result

    async def revise_confirmed_training_goal(
        self, goal_version: int, goal: TrainingGoalUpdate, *, user_confirmed: bool
    ) -> GoalMutationResult:
        _require_confirmation(user_confirmed)
        if goal_version < 1:
            raise ValueError("goal_version must be at least 1")
        result = await self._database_call(lambda: self._repository.revise_goal(goal_version, goal))
        if result is None:
            raise ResourceNotFoundError("Active training goal version was not found")
        return result

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

    async def get_training_metrics(self, window_days: int = 28) -> TrainingMetrics:
        if not 7 <= window_days <= 365:
            raise ValueError("window_days must be between 7 and 365")
        athlete = await self.get_athlete_summary()
        if athlete.training_days_per_week is None:
            raise ResourceNotFoundError(
                "Athlete profile is required to calculate adherence against a target"
            )
        now = datetime.now(UTC)
        try:
            summary = await self._metrics.summary(
                as_of=now,
                window_days=window_days,
                target_sessions_per_week=Decimal(athlete.training_days_per_week),
            )
        except MetricsError as exc:
            raise BackendUnavailableError("Training metrics are unavailable") from exc
        return TrainingMetrics(
            evidence_id=f"metrics:summary:{window_days}d:{now.date().isoformat()}",
            period_start=now - timedelta(days=window_days),
            period_end=now,
            window_days=window_days,
            workouts=summary.workouts,
            total_reps=summary.total_reps,
            total_volume_kg_reps=str(summary.total_volume_kg_reps),
            adherence=AdherenceSummary(
                window_days=summary.adherence.window_days,
                target_sessions_per_week=str(summary.adherence.target_sessions_per_week),
                expected_sessions=str(summary.adherence.expected_sessions),
                completed_sessions=summary.adherence.completed_sessions,
                adherence_percent=str(summary.adherence.adherence_percent),
                matched_routine_sessions=summary.adherence.matched_routine_sessions,
            ),
            stalled_exercises=[_stagnation_summary(item) for item in summary.stalled_exercises],
        )

    async def get_exercise_progress(
        self, exercise_template_id: str, window_days: int = 180
    ) -> ExerciseProgressReport:
        normalized_id = _validated_identifier(exercise_template_id, "exercise_template_id")
        if not 30 <= window_days <= 730:
            raise ValueError("window_days must be between 30 and 730")
        exists = await self._database_call(
            lambda: self._repository.exercise_template_exists(normalized_id)
        )
        if not exists:
            raise ResourceNotFoundError("Exercise template was not found")
        now = datetime.now(UTC)
        try:
            report = await self._metrics.exercise_report(
                normalized_id,
                as_of=now,
                window_days=window_days,
            )
        except MetricsError as exc:
            raise BackendUnavailableError("Exercise progress is unavailable") from exc
        progress = report.progress
        return ExerciseProgressReport(
            evidence_id=(
                f"metrics:exercise:{normalized_id}:{window_days}d:{now.date().isoformat()}"
            ),
            exercise_template_external_id=normalized_id,
            period_start=now - timedelta(days=window_days),
            period_end=now,
            latest_e1rm_kg=_decimal_string(progress.latest_e1rm_kg),
            previous_e1rm_kg=_decimal_string(progress.previous_e1rm_kg),
            e1rm_change_kg=_decimal_string(progress.e1rm_change_kg),
            e1rm_change_percent=_decimal_string(progress.e1rm_change_percent),
            stagnation=_stagnation_summary(report.stagnation),
            sessions=[
                ExerciseSessionSummary(
                    workout_external_id=item.workout_external_id,
                    performed_at=item.performed_at,
                    total_reps=item.total_reps,
                    volume_kg_reps=str(item.volume_kg_reps),
                    best_e1rm_kg=_decimal_string(item.best_e1rm_kg),
                    qualifying_sets=item.qualifying_sets,
                )
                for item in progress.sessions
            ],
        )

    async def create_training_plan_proposal(
        self, plan: TrainingPlanProposalInput, *, user_requested: bool
    ) -> TrainingPlanProposal:
        if user_requested is not True:
            raise ValueError("The athlete must explicitly request a training plan proposal")
        result = await self._database_call(lambda: self._repository.create_plan_proposal(plan))
        if result is None:
            raise ResourceNotFoundError(
                "Athlete profile is required before creating a training plan proposal"
            )
        return result

    async def get_training_plan_proposal(self, proposal_id: UUID) -> TrainingPlanProposal:
        result = await self._database_call(lambda: self._repository.get_plan_proposal(proposal_id))
        if result is None:
            raise ResourceNotFoundError("Training plan proposal was not found")
        return result

    async def compare_training_plan_proposal(self, proposal_id: UUID) -> TrainingPlanComparison:
        result = await self._database_call(
            lambda: self._repository.compare_plan_proposal(proposal_id)
        )
        if result is None:
            raise ResourceNotFoundError("Training plan proposal was not found")
        return result

    async def decide_training_plan_proposal(
        self,
        proposal_id: UUID,
        decision: Literal["approved", "rejected"],
        *,
        user_confirmed: bool,
    ) -> PlanDecisionResult:
        _require_confirmation(user_confirmed)
        try:
            result = await self._database_call(
                lambda: self._repository.decide_plan_proposal(proposal_id, decision)
            )
        except ValueError as exc:
            raise ValueError("Only draft proposals can be approved or rejected") from exc
        if result is None:
            raise ResourceNotFoundError("Training plan proposal was not found")
        return result

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


def _require_confirmation(user_confirmed: bool) -> None:
    if user_confirmed is not True:
        raise ValueError(
            "Explicit athlete confirmation is required after showing a structured summary"
        )


def _decimal_string(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _stagnation_summary(value: StagnationResult) -> StagnationSummary:
    return StagnationSummary(
        exercise_template_external_id=value.exercise_template_external_id,
        is_stalled=value.is_stalled,
        reason=value.reason,
        qualifying_sessions=value.qualifying_sessions,
        span_days=value.span_days,
        improvement_percent=_decimal_string(value.improvement_percent),
    )


def _application_version() -> str:
    try:
        return version("gym-coach")
    except PackageNotFoundError:
        return "0.1.0"
