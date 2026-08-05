from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gym_coach.metrics.calculations import (
    calculate_exercise_progress,
    calculate_summary,
    detect_stagnation,
)
from gym_coach.metrics.types import (
    DEFAULT_STAGNATION_RULE,
    ExerciseProgress,
    MetricsSummary,
    StagnationResult,
    StagnationRule,
)
from gym_coach.persistence.metrics_repository import MetricsRepository


@dataclass(frozen=True, slots=True)
class ExerciseReport:
    progress: ExerciseProgress
    stagnation: StagnationResult


class MetricsError(Exception):
    """Metrics could not be loaded or calculated safely."""


class MetricsService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def summary(
        self,
        *,
        as_of: datetime,
        window_days: int,
        target_sessions_per_week: Decimal,
        stagnation_rule: StagnationRule = DEFAULT_STAGNATION_RULE,
    ) -> MetricsSummary:
        try:
            async with self._session_factory() as session:
                workouts, performances = await MetricsRepository(session).load_history(
                    since=as_of - timedelta(days=window_days)
                )
        except SQLAlchemyError as exc:
            raise MetricsError("Could not load metrics from PostgreSQL") from exc
        return calculate_summary(
            workouts,
            performances,
            as_of=as_of,
            window_days=window_days,
            target_sessions_per_week=target_sessions_per_week,
            stagnation_rule=stagnation_rule,
        )

    async def exercise_report(
        self,
        exercise_template_external_id: str,
        *,
        as_of: datetime,
        window_days: int,
        stagnation_rule: StagnationRule = DEFAULT_STAGNATION_RULE,
    ) -> ExerciseReport:
        if window_days < 1:
            raise ValueError("window_days must be at least 1")
        try:
            async with self._session_factory() as session:
                _, performances = await MetricsRepository(session).load_history(
                    since=as_of - timedelta(days=window_days)
                )
        except SQLAlchemyError as exc:
            raise MetricsError("Could not load metrics from PostgreSQL") from exc
        progress = calculate_exercise_progress(exercise_template_external_id, performances)
        return ExerciseReport(
            progress=progress,
            stagnation=detect_stagnation(
                exercise_template_external_id, progress.sessions, stagnation_rule
            ),
        )

    async def exercise_reports(
        self,
        exercise_template_external_ids: list[str],
        *,
        as_of: datetime,
        window_days: int,
        stagnation_rule: StagnationRule = DEFAULT_STAGNATION_RULE,
    ) -> tuple[ExerciseReport, ...]:
        if window_days < 1:
            raise ValueError("window_days must be at least 1")
        unique_ids = tuple(dict.fromkeys(exercise_template_external_ids))
        try:
            async with self._session_factory() as session:
                _, performances = await MetricsRepository(session).load_history(
                    since=as_of - timedelta(days=window_days)
                )
        except SQLAlchemyError as exc:
            raise MetricsError("Could not load metrics from PostgreSQL") from exc
        reports = []
        for template_id in unique_ids:
            progress = calculate_exercise_progress(template_id, performances)
            reports.append(
                ExerciseReport(
                    progress=progress,
                    stagnation=detect_stagnation(template_id, progress.sessions, stagnation_rule),
                )
            )
        return tuple(reports)
