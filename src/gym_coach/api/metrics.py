from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from gym_coach.config import get_settings
from gym_coach.db import create_engine, create_session_factory
from gym_coach.metrics.service import ExerciseReport, MetricsError, MetricsService
from gym_coach.metrics.types import MetricsSummary

router = APIRouter(prefix="/metrics", tags=["metrics"])


async def get_metrics_service() -> AsyncIterator[MetricsService]:
    engine = create_engine(get_settings().database_url)
    try:
        yield MetricsService(create_session_factory(engine))
    finally:
        await engine.dispose()


MetricsDependency = Annotated[MetricsService, Depends(get_metrics_service)]


@router.get("/summary", response_model=MetricsSummary)
async def metrics_summary(
    service: MetricsDependency,
    days: Annotated[int, Query(ge=1, le=366)] = 28,
    target_sessions_per_week: Annotated[Decimal, Query(gt=0, le=14)] = Decimal(4),
) -> MetricsSummary:
    try:
        return await service.summary(
            as_of=datetime.now(UTC),
            window_days=days,
            target_sessions_per_week=target_sessions_per_week,
        )
    except MetricsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/exercises/{exercise_template_id}", response_model=ExerciseReport)
async def exercise_metrics(
    exercise_template_id: str,
    service: MetricsDependency,
    days: Annotated[int, Query(ge=1, le=730)] = 180,
) -> ExerciseReport:
    try:
        return await service.exercise_report(
            exercise_template_id,
            as_of=datetime.now(UTC),
            window_days=days,
        )
    except MetricsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
