import re
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib.metadata import PackageNotFoundError, version
from typing import Literal, Protocol, Self
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from gym_coach.config import Settings
from gym_coach.integrations.hevy.client import routine_matches_write_request
from gym_coach.integrations.hevy.errors import (
    HevyError,
    HevyHTTPError,
    HevyInvalidResponseError,
    HevyTimeoutError,
    HevyTransportError,
)
from gym_coach.integrations.hevy.schemas import (
    RepRange,
    Routine,
    RoutineWriteData,
    RoutineWriteExercise,
    RoutineWriteRequest,
    RoutineWriteSet,
    UserInfo,
)
from gym_coach.mcp.errors import BackendUnavailableError, ResourceNotFoundError
from gym_coach.mcp.schemas import (
    AdherenceSummary,
    AthleteCheckInInput,
    AthleteCheckInView,
    AthleteMeasurementInput,
    AthleteMeasurementView,
    AthleteProfileUpdate,
    AthleteSummary,
    CoachingAssessment,
    ComponentStatus,
    ExerciseProgressReport,
    ExerciseSessionSummary,
    ExerciseTemplateSearchResults,
    GoalMutationResult,
    HevyConnectionStatus,
    HevySyncResult,
    OnboardingStatus,
    PlanDecisionResult,
    ProfileMutationResult,
    RecentWorkouts,
    RoutineApplicationCommand,
    RoutineApplicationPreview,
    RoutineApplicationReconciliationContext,
    RoutineApplicationReconciliationResult,
    RoutineApplicationResult,
    RoutineList,
    StagnationSummary,
    SystemStatus,
    TrainingGoalUpdate,
    TrainingHistoryAssessment,
    TrainingMetrics,
    TrainingPlanComparison,
    TrainingPlanProposal,
    TrainingPlanProposalInput,
    TrainingRoutine,
    TrainingWorkout,
    VerifiedPlanEvidence,
    WorkoutReviewAcknowledgement,
)
from gym_coach.metrics.service import ExerciseReport, MetricsError
from gym_coach.metrics.types import MetricsSummary, StagnationResult
from gym_coach.nutrition.service import NutritionService
from gym_coach.sync.hevy import HevySyncError, routine_content_hash
from gym_coach.sync.types import SyncResult as HevySyncRun
from gym_coach.tracking.training import WorkoutComparison, compare_workout

MAX_RECENT_WORKOUTS = 50
MAX_EXERCISE_RESULTS = 25
_DATE_PATTERN = r"\d{4}-\d{2}-\d{2}"
_SUMMARY_EVIDENCE = re.compile(rf"metrics:summary:(?P<days>\d{{1,3}})d:{_DATE_PATTERN}")
_EXERCISE_EVIDENCE = re.compile(
    rf"metrics:exercise:(?P<template_id>[a-z0-9_.-]+):(?P<days>\d{{1,3}})d:{_DATE_PATTERN}"
)
_ROUTINE_EVIDENCE = re.compile(r"routine:(?P<routine_id>[a-z0-9_.-]+)")
_PROFILE_EVIDENCE = re.compile(r"profile:(?P<version>\d+)")
_GOAL_EVIDENCE = re.compile(r"goal:(?P<version>\d+)")
_HISTORY_EVIDENCE = re.compile(rf"history:assessment:{_DATE_PATTERN}")


class HevyStatusClient(Protocol):
    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, *args: object) -> None: ...

    async def get_user(self) -> UserInfo: ...

    async def get_routine(self, routine_id: str) -> Routine: ...

    async def get_all_routines(self) -> list[Routine]: ...

    async def create_routine(self, request: RoutineWriteRequest) -> Routine: ...

    async def update_routine(self, routine_id: str, request: RoutineWriteRequest) -> Routine: ...


HevyClientFactory = Callable[[], HevyStatusClient]


class HevySyncRunner(Protocol):
    async def sync(self) -> HevySyncRun: ...


HevySyncFactory = Callable[[], HevySyncRunner]


class MCPReadRepository(Protocol):
    async def is_available(self) -> bool: ...

    async def athlete_summary(self) -> AthleteSummary: ...

    async def onboarding_status(self) -> OnboardingStatus: ...

    async def training_history_assessment(self) -> TrainingHistoryAssessment: ...

    async def coaching_assessment(self) -> CoachingAssessment: ...

    async def save_profile(self, data: AthleteProfileUpdate) -> ProfileMutationResult: ...

    async def save_measurement(
        self, data: AthleteMeasurementInput
    ) -> AthleteMeasurementView | None: ...

    async def save_check_in(self, data: AthleteCheckInInput) -> AthleteCheckInView | None: ...

    async def add_goal(self, data: TrainingGoalUpdate) -> GoalMutationResult | None: ...

    async def revise_goal(
        self, goal_version: int, data: TrainingGoalUpdate
    ) -> GoalMutationResult | None: ...

    async def list_routines(self) -> RoutineList: ...

    async def get_routine(self, external_id: str) -> TrainingRoutine | None: ...

    async def recent_workouts(self, limit: int) -> RecentWorkouts: ...

    async def get_workout(self, external_id: str) -> TrainingWorkout | None: ...

    async def get_workout_prescription(
        self, workout_id: str
    ) -> tuple[TrainingRoutine, Literal["historical_snapshot", "current_fallback"]] | None: ...

    async def search_exercise_templates(
        self, query: str, limit: int
    ) -> ExerciseTemplateSearchResults: ...

    async def exercise_template_exists(self, external_id: str) -> bool: ...

    async def create_plan_proposal(
        self, data: TrainingPlanProposalInput, evidence: list[VerifiedPlanEvidence]
    ) -> TrainingPlanProposal | None: ...

    async def get_plan_proposal(self, proposal_id: UUID) -> TrainingPlanProposal | None: ...

    async def compare_plan_proposal(self, proposal_id: UUID) -> TrainingPlanComparison | None: ...

    async def decide_plan_proposal(
        self, proposal_id: UUID, decision: Literal["approved", "rejected"]
    ) -> PlanDecisionResult | None: ...

    async def acknowledge_workout_review(
        self, review_id: UUID
    ) -> WorkoutReviewAcknowledgement | None: ...

    async def prepare_routine_application(
        self, proposal_id: UUID
    ) -> RoutineApplicationPreview | None: ...

    async def claim_routine_application(
        self, proposal_id: UUID, confirmation_token: str
    ) -> RoutineApplicationCommand | None: ...

    async def finish_routine_application(
        self,
        application_id: UUID,
        *,
        status: Literal["applied", "failed", "uncertain", "partial"],
        routine_ids: list[str],
        error_type: str | None,
    ) -> None: ...

    async def get_routine_application_reconciliation_context(
        self, proposal_id: UUID
    ) -> RoutineApplicationReconciliationContext | None: ...

    async def reconcile_routine_application(
        self,
        application_id: UUID,
        *,
        status: Literal["applied", "partial", "uncertain"],
        routine_ids: list[str],
        error_type: str | None,
    ) -> None: ...


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
        hevy_sync_factory: HevySyncFactory | None = None,
        nutrition: NutritionService | None = None,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._metrics = metrics
        self._hevy_client_factory = hevy_client_factory
        self._hevy_sync_factory = hevy_sync_factory
        self.nutrition = nutrition

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

    async def sync_hevy(self, *, user_confirmed: bool) -> HevySyncResult:
        _require_confirmation(user_confirmed)
        if self._hevy_sync_factory is None:
            raise ValueError("Hevy synchronization is not configured")
        try:
            result = await self._hevy_sync_factory().sync()
        except (HevyError, HevySyncError) as exc:
            raise ValueError(
                "Hevy synchronization failed safely; no routine write was attempted"
            ) from exc
        return HevySyncResult(
            run_id=result.run_id,
            inserted=result.counts.inserted,
            updated=result.counts.updated,
            unchanged=result.counts.unchanged,
            deleted=result.counts.deleted,
        )

    async def get_athlete_summary(self) -> AthleteSummary:
        return await self._database_call(self._repository.athlete_summary)

    async def get_onboarding_status(self) -> OnboardingStatus:
        return await self._database_call(self._repository.onboarding_status)

    async def get_training_history_assessment(self) -> TrainingHistoryAssessment:
        return await self._database_call(self._repository.training_history_assessment)

    async def get_coaching_assessment(self) -> CoachingAssessment:
        return await self._database_call(self._repository.coaching_assessment)

    async def save_confirmed_athlete_profile(
        self, profile: AthleteProfileUpdate, *, user_confirmed: bool
    ) -> ProfileMutationResult:
        _require_confirmation(user_confirmed)
        return await self._database_call(lambda: self._repository.save_profile(profile))

    async def save_confirmed_athlete_measurement(
        self, measurement: AthleteMeasurementInput, *, user_confirmed: bool
    ) -> AthleteMeasurementView:
        _require_confirmation(user_confirmed)
        result = await self._database_call(lambda: self._repository.save_measurement(measurement))
        if result is None:
            raise ResourceNotFoundError("Athlete profile must be configured before measurements")
        return result

    async def save_confirmed_athlete_check_in(
        self, check_in: AthleteCheckInInput, *, user_confirmed: bool
    ) -> AthleteCheckInView:
        _require_confirmation(user_confirmed)
        result = await self._database_call(lambda: self._repository.save_check_in(check_in))
        if result is None:
            raise ResourceNotFoundError("Athlete profile must be configured before check-ins")
        return result

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

    async def compare_workout_to_prescription(self, workout_id: str) -> WorkoutComparison:
        workout = await self.get_workout(workout_id)
        prescription = await self._database_call(
            lambda: self._repository.get_workout_prescription(workout_id)
        )
        if prescription is None:
            raise ResourceNotFoundError("Workout has no linked routine prescription")
        routine, source = prescription
        return compare_workout(routine, workout, prescription_source=source)

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
        self,
        exercise_template_id: str,
        window_days: int = 180,
        *,
        as_of: datetime | None = None,
    ) -> ExerciseProgressReport:
        normalized_id = _validated_identifier(exercise_template_id, "exercise_template_id")
        if not 30 <= window_days <= 730:
            raise ValueError("window_days must be between 30 and 730")
        exists = await self._database_call(
            lambda: self._repository.exercise_template_exists(normalized_id)
        )
        if not exists:
            raise ResourceNotFoundError("Exercise template was not found")
        now = as_of or datetime.now(UTC)
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
            progress_metric=progress.progress_metric,
            latest_metric_value=_decimal_string(progress.latest_metric_value),
            previous_metric_value=_decimal_string(progress.previous_metric_value),
            best_metric_value=_decimal_string(progress.best_metric_value),
            metric_change_percent=_decimal_string(progress.metric_change_percent),
            latest_is_personal_record=progress.latest_is_personal_record,
            stagnation=_stagnation_summary(report.stagnation),
            sessions=[
                ExerciseSessionSummary(
                    workout_external_id=item.workout_external_id,
                    performed_at=item.performed_at,
                    total_reps=item.total_reps,
                    volume_kg_reps=str(item.volume_kg_reps),
                    best_e1rm_kg=_decimal_string(item.best_e1rm_kg),
                    qualifying_sets=item.qualifying_sets,
                    working_sets=item.working_sets,
                    best_weight_kg=_decimal_string(item.best_weight_kg),
                    minimum_weight_kg=_decimal_string(item.minimum_weight_kg),
                    max_reps=item.max_reps,
                    total_distance_meters=str(item.total_distance_meters),
                    total_duration_seconds=item.total_duration_seconds,
                    mean_rpe=_decimal_string(item.mean_rpe),
                )
                for item in progress.sessions
            ],
        )

    async def create_training_plan_proposal(
        self, plan: TrainingPlanProposalInput, *, user_requested: bool
    ) -> TrainingPlanProposal:
        if user_requested is not True:
            raise ValueError("The athlete must explicitly request a training plan proposal")
        if not plan.changes:
            raise ValueError("Each proposal must justify at least one change with evidence_ids")
        evidence = await self._resolve_plan_evidence(plan.evidence_ids)
        result = await self._database_call(
            lambda: self._repository.create_plan_proposal(plan, evidence)
        )
        if result is None:
            raise ResourceNotFoundError(
                "Athlete profile is required before creating a training plan proposal"
            )
        return result

    async def _resolve_plan_evidence(self, evidence_ids: list[str]) -> list[VerifiedPlanEvidence]:
        athlete: AthleteSummary | None = None
        resolved: list[VerifiedPlanEvidence] = []
        for evidence_id in dict.fromkeys(evidence_ids):
            if _HISTORY_EVIDENCE.fullmatch(evidence_id):
                history = await self.get_training_history_assessment()
                if history.evidence_id != evidence_id:
                    raise ValueError("history evidence is stale; request a fresh assessment")
                resolved.append(
                    VerifiedPlanEvidence(
                        evidence_id=evidence_id,
                        category="history",
                        description="Deterministic training-history assessment",
                        value=(
                            f"level={history.history_level}; confidence={history.confidence}; "
                            f"workouts={history.workout_count}; days={history.calendar_days}; "
                            f"distinct_exercises={history.distinct_exercise_count}"
                        ),
                        period_start=history.period_start,
                        period_end=history.period_end,
                    )
                )
                continue
            if match := _SUMMARY_EVIDENCE.fullmatch(evidence_id):
                summary_metric = await self.get_training_metrics(int(match.group("days")))
                if summary_metric.evidence_id != evidence_id:
                    raise ValueError("metrics evidence is stale; request fresh metrics")
                resolved.append(
                    VerifiedPlanEvidence(
                        evidence_id=evidence_id,
                        category="metric",
                        description="Deterministic training summary",
                        value=(
                            f"workouts={summary_metric.workouts}; "
                            f"total_reps={summary_metric.total_reps}; "
                            f"volume_kg_reps={summary_metric.total_volume_kg_reps}; "
                            f"adherence_percent={summary_metric.adherence.adherence_percent}"
                        ),
                        period_start=summary_metric.period_start,
                        period_end=summary_metric.period_end,
                    )
                )
                continue
            if match := _EXERCISE_EVIDENCE.fullmatch(evidence_id):
                exercise_metric = await self.get_exercise_progress(
                    match.group("template_id"), int(match.group("days"))
                )
                if exercise_metric.evidence_id != evidence_id:
                    raise ValueError("exercise evidence is stale; request fresh progress metrics")
                resolved.append(
                    VerifiedPlanEvidence(
                        evidence_id=evidence_id,
                        category="metric",
                        description="Deterministic exercise progress",
                        value=(
                            f"latest_e1rm_kg={exercise_metric.latest_e1rm_kg}; "
                            f"change_percent={exercise_metric.e1rm_change_percent}; "
                            f"stalled={exercise_metric.stagnation.is_stalled}; "
                            f"reason={exercise_metric.stagnation.reason}"
                        ),
                        period_start=exercise_metric.period_start,
                        period_end=exercise_metric.period_end,
                    )
                )
                continue
            if match := _ROUTINE_EVIDENCE.fullmatch(evidence_id):
                routine = await self.get_training_routine(match.group("routine_id"))
                resolved.append(
                    VerifiedPlanEvidence(
                        evidence_id=evidence_id,
                        category="routine",
                        description="Active synchronized training routine",
                        value=(
                            f"title={routine.title}; exercises={len(routine.exercises)}; "
                            f"sets={sum(len(item.sets) for item in routine.exercises)}"
                        ),
                    )
                )
                continue
            if athlete is None:
                athlete = await self.get_athlete_summary()
            if match := _PROFILE_EVIDENCE.fullmatch(evidence_id):
                if athlete.profile_version != int(match.group("version")):
                    raise ValueError("profile evidence does not match the current profile version")
                resolved.append(
                    VerifiedPlanEvidence(
                        evidence_id=evidence_id,
                        category="profile",
                        description="Confirmed athlete profile version",
                        value=f"version={athlete.profile_version}",
                    )
                )
                continue
            if match := _GOAL_EVIDENCE.fullmatch(evidence_id):
                goal_version = int(match.group("version"))
                goal = next((item for item in athlete.goals if item.version == goal_version), None)
                if goal is None:
                    raise ValueError("goal evidence does not identify an active goal")
                resolved.append(
                    VerifiedPlanEvidence(
                        evidence_id=evidence_id,
                        category="goal",
                        description="Confirmed active training goal",
                        value=(
                            f"type={goal.goal_type}; priority={goal.priority}; "
                            f"description={goal.description}"
                        ),
                    )
                )
                continue
            raise ValueError("proposal contains an unknown or unverifiable evidence_id")
        return resolved

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

    async def preview_training_plan_application(
        self, proposal_id: UUID
    ) -> RoutineApplicationPreview:
        result = await self._database_call(
            lambda: self._repository.prepare_routine_application(proposal_id)
        )
        if result is None:
            raise ResourceNotFoundError("Training plan proposal was not found")
        return result

    async def apply_training_plan_to_hevy(
        self,
        proposal_id: UUID,
        confirmation_token: str,
        *,
        user_confirmed: bool,
    ) -> RoutineApplicationResult:
        _require_confirmation(user_confirmed)
        if (
            self._settings.hevy_api_key is None
            or not self._settings.hevy_api_key.get_secret_value()
        ):
            raise ValueError("HEVY_API_KEY must be configured before applying a routine")
        command = await self._database_call(
            lambda: self._repository.claim_routine_application(
                proposal_id, confirmation_token.strip()
            )
        )
        if command is None:
            raise ResourceNotFoundError("Prepared routine application was not found")
        routine_ids: list[str] = []
        status: Literal["applied", "failed", "uncertain", "partial"] = "applied"
        error_type: str | None = None
        sync_status: Literal["not_configured", "not_run", "succeeded", "failed"] = (
            "not_configured" if self._hevy_sync_factory is None else "not_run"
        )
        try:
            async with self._hevy_client_factory() as client:
                if command.action == "update":
                    if command.source_routine_id is None or command.source_routine_hash is None:
                        raise ValueError("Prepared update has no source routine")
                    current = await client.get_routine(command.source_routine_id)
                    if routine_content_hash(current) != command.source_routine_hash:
                        status = "failed"
                        error_type = "stale_routine"
                    else:
                        routine = await client.update_routine(
                            command.source_routine_id,
                            _routine_request(command.plan.workouts[0]),
                        )
                        routine_ids.append(routine.id)
                else:
                    for workout in command.plan.workouts:
                        routine = await client.create_routine(_routine_request(workout))
                        routine_ids.append(routine.id)
        except (HevyTimeoutError, HevyTransportError) as exc:
            status = "partial" if routine_ids else "uncertain"
            error_type = _hevy_application_error_code(exc)
        except HevyInvalidResponseError as exc:
            # A successful HTTP write followed by an invalid response can still have
            # changed Hevy. Never classify it as safely retryable.
            status = "partial" if routine_ids else "uncertain"
            error_type = _hevy_application_error_code(exc)
        except HevyHTTPError as exc:
            status = "partial" if routine_ids else "failed"
            error_type = _hevy_application_error_code(exc)
        except HevyError as exc:
            status = "partial" if routine_ids else "failed"
            error_type = _hevy_application_error_code(exc)
        if status in {"applied", "partial"} and routine_ids and self._hevy_sync_factory is not None:
            try:
                await self._hevy_sync_factory().sync()
                sync_status = "succeeded"
            except (HevyError, HevySyncError, SQLAlchemyError):
                # The remote write remains classified from its own response. A failed
                # post-write sync is observable without turning a confirmed Hevy write
                # into a retryable application failure.
                sync_status = "failed"
        await self._database_call(
            lambda: self._repository.finish_routine_application(
                command.application_id,
                status=status,
                routine_ids=routine_ids,
                error_type=error_type,
            )
        )
        return RoutineApplicationResult(
            application_id=command.application_id,
            proposal_id=proposal_id,
            action=command.action,
            status=status,
            routine_ids=routine_ids,
            error_code=error_type,
            sync_status=sync_status,
            message=_routine_application_message(status, error_type, sync_status),
        )

    async def reconcile_training_plan_application(
        self, proposal_id: UUID, *, user_confirmed: bool
    ) -> RoutineApplicationReconciliationResult:
        _require_confirmation(user_confirmed)
        context = await self._database_call(
            lambda: self._repository.get_routine_application_reconciliation_context(proposal_id)
        )
        if context is None:
            raise ResourceNotFoundError("Routine application was not found")
        if context.action == "update":
            if context.plan.source_routine_id is None or len(context.plan.workouts) != 1:
                raise ValueError("Prepared update has no single source routine")
            async with self._hevy_client_factory() as client:
                routine = await client.get_routine(context.plan.source_routine_id)
            if routine_matches_write_request(routine, _routine_request(context.plan.workouts[0])):
                matched_indexes = [0]
                matched_ids = [routine.id]
            else:
                matched_indexes = []
                matched_ids = []
        else:
            async with self._hevy_client_factory() as client:
                routines = await client.get_all_routines()
            cutoff = context.applied_at - timedelta(minutes=5)
            recent = [
                routine
                for routine in routines
                if routine.created_at is not None and routine.created_at >= cutoff
            ]
            recorded_count = min(len(context.recorded_routine_ids), len(context.plan.workouts))
            matched_indexes = list(range(recorded_count))
            matched_ids = list(context.recorded_routine_ids)
            used_ids = set(matched_ids)
            for index, workout in enumerate(context.plan.workouts[recorded_count:], recorded_count):
                matches = [
                    routine
                    for routine in recent
                    if routine.id not in used_ids
                    and routine_matches_write_request(routine, _routine_request(workout))
                ]
                if len(matches) == 1:
                    matched_indexes.append(index)
                    matched_ids.append(matches[0].id)
                    used_ids.add(matches[0].id)

        matched_ids = list(dict.fromkeys(matched_ids))
        if len(matched_indexes) == len(context.plan.workouts):
            status: Literal["applied", "partial", "uncertain"] = "applied"
            error_code = None
        elif matched_ids:
            status = "partial"
            error_code = "reconciled_partial"
        else:
            status = "uncertain"
            error_code = "hevy_invalid_response"
        await self._database_call(
            lambda: self._repository.reconcile_routine_application(
                context.application_id,
                status=status,
                routine_ids=matched_ids,
                error_type=error_code,
            )
        )
        sync_status: Literal["not_configured", "not_run", "succeeded", "failed"] = (
            "not_configured" if self._hevy_sync_factory is None else "not_run"
        )
        if matched_ids and self._hevy_sync_factory is not None:
            try:
                await self._hevy_sync_factory().sync()
                sync_status = "succeeded"
            except (HevyError, HevySyncError, SQLAlchemyError):
                sync_status = "failed"
        return RoutineApplicationReconciliationResult(
            application_id=context.application_id,
            proposal_id=proposal_id,
            status=status,
            matched_workout_indexes=matched_indexes,
            routine_ids=matched_ids,
            error_code=error_code,
            sync_status=sync_status,
            message=(
                "Remote Hevy routines were compared with the exact approved plan. "
                "Create a new proposal containing only unmatched workout indexes."
                if status == "partial"
                else "Remote Hevy routines were compared with the exact approved plan."
            ),
        )

    async def acknowledge_automatic_workout_review(
        self, review_id: UUID
    ) -> WorkoutReviewAcknowledgement:
        result = await self._database_call(
            lambda: self._repository.acknowledge_workout_review(review_id)
        )
        if result is None:
            raise ResourceNotFoundError("Workout review is not pending acknowledgement")
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


def _routine_request(workout: object) -> RoutineWriteRequest:
    from gym_coach.mcp.schemas import ProposedPlanWorkout

    planned = ProposedPlanWorkout.model_validate(workout)
    superset_ids: dict[str, int] = {}
    return RoutineWriteRequest(
        routine=RoutineWriteData(
            title=planned.title,
            exercises=[
                RoutineWriteExercise(
                    exercise_template_id=exercise.exercise_template_external_id or "",
                    rest_seconds=exercise.rest_seconds,
                    notes=_exercise_notes(exercise.notes, exercise.sets),
                    superset_id=(
                        superset_ids.setdefault(exercise.superset_group, len(superset_ids) + 1)
                        if exercise.superset_group is not None
                        else None
                    ),
                    sets=[_routine_set(item) for item in exercise.sets],
                )
                for exercise in planned.exercises
            ],
        )
    )


def _routine_set(item: object) -> RoutineWriteSet:
    from gym_coach.mcp.schemas import ProposedPlanSet

    planned = ProposedPlanSet.model_validate(item)
    set_type = "dropset" if planned.set_type == "drop" else planned.set_type
    return RoutineWriteSet(
        set_type=set_type,
        weight_kg=float(planned.weight_kg) if planned.weight_kg is not None else None,
        reps=None,
        rep_range=(
            RepRange(start=planned.reps_min, end=planned.reps_max)
            if planned.reps_min is not None and planned.reps_max is not None
            else None
        ),
        duration_seconds=planned.duration_seconds_min,
        distance_meters=(
            int(planned.distance_meters_min) if planned.distance_meters_min is not None else None
        ),
    )


def _exercise_notes(base_notes: str | None, sets: Sequence[object]) -> str | None:
    from gym_coach.mcp.schemas import ProposedPlanSet

    guidance = list(
        dict.fromkeys(
            item.load_guidance
            for item in (ProposedPlanSet.model_validate(value) for value in sets)
            if item.load_guidance
        )
    )
    parts = [part for part in (base_notes, *guidance) if part]
    return " | ".join(parts) if parts else None


def _require_confirmation(user_confirmed: bool) -> None:
    if user_confirmed is not True:
        raise ValueError(
            "Explicit athlete confirmation is required after showing a structured summary"
        )


def _hevy_application_error_code(exc: HevyError) -> str:
    if isinstance(exc, HevyHTTPError):
        return f"hevy_http_{exc.status_code}"
    if isinstance(exc, HevyInvalidResponseError):
        return "hevy_invalid_response"
    if isinstance(exc, HevyTimeoutError):
        return "hevy_timeout"
    if isinstance(exc, HevyTransportError):
        return "hevy_transport"
    return "hevy_error"


def _routine_application_message(
    status: Literal["applied", "failed", "uncertain", "partial"],
    error_code: str | None,
    sync_status: Literal["not_configured", "not_run", "succeeded", "failed"] = "not_run",
) -> str:
    sync_note = ""
    if sync_status == "succeeded":
        sync_note = " PostgreSQL was synchronized with the current Hevy snapshot."
    elif sync_status == "failed":
        sync_note = (
            " The Hevy write result is preserved, but PostgreSQL synchronization failed; "
            "the next sync will retry it."
        )
    if status == "applied":
        return "The exact approved plan was applied to Hevy." + sync_note
    diagnostic = f" Safe diagnostic: {error_code}." if error_code is not None else ""
    if status == "failed":
        return (
            "Hevy rejected the exact write before any routine was confirmed."
            f"{diagnostic} Correct the cause and prepare a new preview before retrying.{sync_note}"
        )
    if status == "partial":
        return (
            "Only part of the approved plan was confirmed in Hevy."
            f"{diagnostic} Reconcile the remote routines and do not retry automatically.{sync_note}"
        )
    return (
        "The remote outcome could not be confirmed."
        f"{diagnostic} Reconcile Hevy and do not retry automatically.{sync_note}"
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
