import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pydantic_ai import Agent
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gym_coach.coach.errors import (
    CoachConfigurationError,
    CoachEvidenceError,
    CoachPersistenceError,
)
from gym_coach.coach.schemas import (
    AthleteProfileView,
    CoachContext,
    CoachResponse,
    EvidenceFact,
    RoutineContext,
    StoredProposalView,
    TrainingGoalView,
)
from gym_coach.metrics.service import ExerciseReport, MetricsService
from gym_coach.metrics.types import MetricsSummary
from gym_coach.persistence.coach_repository import CoachRepository

COACH_INSTRUCTIONS = """
Eres un entrenador personal prudente y basado en evidencia. Responde en el idioma del usuario.
Interpreta exclusivamente el contexto proporcionado. Las métricas ya están calculadas: nunca las
recalcules ni inventes valores. La respuesta general, cada hallazgo y cada propuesta deben citar
uno o más evidence_ids existentes. Distingue hechos de recomendaciones. Si faltan datos, dilo y
pide el dato mínimo.
Puedes revisar rutinas, proponer una rutina nueva o una mejora, pero jamás afirmes que la has
aplicado. Una propuesta será solo un borrador pendiente de aprobación local y no modificará Hevy.
No diagnostiques lesiones ni sustituyas atención médica.
""".strip()


@dataclass(frozen=True, slots=True)
class CoachRunResult:
    response: CoachResponse
    stored_proposal: StoredProposalView | None


class CoachService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        model: Model,
        model_name: str,
    ) -> None:
        self._session_factory = session_factory
        self._model_name = model_name
        self._agent = Agent(
            model,
            output_type=CoachResponse,
            instructions=COACH_INSTRUCTIONS,
            retries=2,
        )

    async def ask(self, user_request: str, *, as_of: datetime | None = None) -> CoachRunResult:
        if not user_request.strip():
            raise ValueError("Coach request must not be empty")
        now = as_of or datetime.now(UTC)
        context = await self._build_context(as_of=now)
        prompt = (
            "Solicitud del atleta:\n"
            f"{user_request.strip()}\n\n"
            "Contexto mínimo autorizado (JSON):\n"
            f"{context.model_dump_json(exclude_none=True)}"
        )
        try:
            result = await self._agent.run(
                prompt,
                usage_limits=UsageLimits(
                    request_limit=3,
                    input_tokens_limit=100_000,
                    output_tokens_limit=6_000,
                ),
            )
        except AgentRunError as exc:
            raise CoachConfigurationError(
                "The coach model did not return a valid response"
            ) from exc
        self._validate_evidence(result.output, context.evidence)

        stored = None
        if result.output.proposal is not None:
            referenced = set(result.output.proposal.evidence_ids)
            evidence = [item for item in context.evidence if item.id in referenced]
            try:
                async with self._session_factory.begin() as session:
                    stored = await CoachRepository(session).save_proposal(
                        profile_id=context.profile.id,
                        proposal=result.output.proposal,
                        evidence=evidence,
                        model_name=self._model_name,
                    )
            except SQLAlchemyError as exc:
                raise CoachPersistenceError("Could not save coach proposal in PostgreSQL") from exc
        return CoachRunResult(response=result.output, stored_proposal=stored)

    async def _build_context(self, *, as_of: datetime) -> CoachContext:
        try:
            async with self._session_factory() as session:
                repository = CoachRepository(session)
                profile = await repository.get_profile()
                if profile is None:
                    raise CoachConfigurationError(
                        "Configure the athlete profile before asking the coach"
                    )
                goals = await repository.active_goals(profile.id)
                routines = await repository.active_routines()
        except SQLAlchemyError as exc:
            raise CoachPersistenceError("Could not load coach context from PostgreSQL") from exc

        metrics_service = MetricsService(self._session_factory)
        summary = await metrics_service.summary(
            as_of=as_of,
            window_days=28,
            target_sessions_per_week=Decimal(profile.training_days_per_week),
        )
        exercise_ids = [
            exercise.exercise_template_id for routine in routines for exercise in routine.exercises
        ]
        exercise_reports = await metrics_service.exercise_reports(
            exercise_ids,
            as_of=as_of,
            window_days=180,
        )
        evidence = self._evidence(profile, goals, routines, summary, exercise_reports, as_of)
        return CoachContext(profile=profile, goals=goals, routines=routines, evidence=evidence)

    @staticmethod
    def _evidence(
        profile: AthleteProfileView,
        goals: list[TrainingGoalView],
        routines: list[RoutineContext],
        summary: MetricsSummary,
        exercise_reports: tuple[ExerciseReport, ...],
        as_of: datetime,
    ) -> list[EvidenceFact]:
        start = as_of - timedelta(days=28)
        facts = [
            EvidenceFact(
                id="profile.training_days",
                category="profile",
                description="Días de entrenamiento disponibles por semana",
                value=str(profile.training_days_per_week),
                unit="sessions/week",
            ),
            EvidenceFact(
                id="profile.experience",
                category="profile",
                description="Nivel de experiencia declarado",
                value=profile.experience_level or "not_self_reported",
            ),
            EvidenceFact(
                id="metric.workouts.28d",
                category="metric",
                description="Entrenamientos completados",
                value=str(summary.workouts),
                unit="sessions",
                period_start=start,
                period_end=as_of,
            ),
            EvidenceFact(
                id="metric.volume.28d",
                category="metric",
                description="Volumen externo determinista",
                value=str(summary.total_volume_kg_reps),
                unit="kg_reps",
                period_start=start,
                period_end=as_of,
            ),
            EvidenceFact(
                id="metric.adherence.28d",
                category="metric",
                description="Adherencia al objetivo semanal configurado",
                value=str(summary.adherence.adherence_percent),
                unit="percent",
                period_start=start,
                period_end=as_of,
            ),
        ]
        if profile.session_duration_minutes is not None:
            facts.append(
                EvidenceFact(
                    id="profile.session_minutes",
                    category="profile",
                    description="Duración disponible por sesión",
                    value=str(profile.session_duration_minutes),
                    unit="minutes",
                )
            )
        for category, values in (
            ("equipment", profile.equipment),
            ("limitations", profile.limitations),
            ("preferences", profile.preferences),
        ):
            if values:
                facts.append(
                    EvidenceFact(
                        id=f"profile.{category}",
                        category="profile",
                        description=f"Perfil declarado: {category}",
                        value="; ".join(values),
                    )
                )
        facts.extend(
            EvidenceFact(
                id=f"goal.{goal.version}",
                category="goal",
                description=f"Objetivo activo de prioridad {goal.priority}: {goal.goal_type}",
                value=goal.description,
            )
            for goal in goals
        )
        facts.extend(
            EvidenceFact(
                id=f"routine.{index}",
                category="routine",
                description="Rutina activa sincronizada",
                value=routine.title,
            )
            for index, routine in enumerate(routines, start=1)
        )
        facts.extend(
            EvidenceFact(
                id=f"metric.stalled.{index}",
                category="metric",
                description="Señal determinista de estancamiento",
                value=item.exercise_template_external_id,
                period_start=start,
                period_end=as_of,
            )
            for index, item in enumerate(summary.stalled_exercises, start=1)
        )
        exercise_period_start = as_of - timedelta(days=180)
        for index, report in enumerate(exercise_reports, start=1):
            progress = report.progress
            prefix = f"metric.exercise.{index}"
            if progress.latest_e1rm_kg is not None:
                facts.append(
                    EvidenceFact(
                        id=f"{prefix}.e1rm",
                        category="metric",
                        description=(
                            "e1RM determinista más reciente para "
                            f"{progress.exercise_template_external_id}"
                        ),
                        value=str(progress.latest_e1rm_kg),
                        unit="kg",
                        period_start=exercise_period_start,
                        period_end=as_of,
                    )
                )
            if progress.e1rm_change_percent is not None:
                facts.append(
                    EvidenceFact(
                        id=f"{prefix}.change",
                        category="metric",
                        description=(
                            "Cambio entre las dos últimas e1RM para "
                            f"{progress.exercise_template_external_id}"
                        ),
                        value=str(progress.e1rm_change_percent),
                        unit="percent",
                        period_start=exercise_period_start,
                        period_end=as_of,
                    )
                )
            facts.append(
                EvidenceFact(
                    id=f"{prefix}.stagnation",
                    category="metric",
                    description=(
                        "Evaluación determinista de estancamiento para "
                        f"{progress.exercise_template_external_id}"
                    ),
                    value=report.stagnation.reason,
                    period_start=exercise_period_start,
                    period_end=as_of,
                )
            )
        return facts

    @staticmethod
    def _validate_evidence(response: CoachResponse, available: list[EvidenceFact]) -> None:
        known = {item.id for item in available}
        referenced = set(response.evidence_ids)
        referenced.update(
            {evidence_id for finding in response.findings for evidence_id in finding.evidence_ids}
        )
        if response.proposal is not None:
            referenced.update(response.proposal.evidence_ids)
        unknown = sorted(referenced - known)
        if unknown:
            raise CoachEvidenceError(
                "The coach referenced unavailable evidence: " + json.dumps(unknown)
            )
