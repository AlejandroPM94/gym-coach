from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from pydantic_ai.models.test import TestModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gym_coach.coach.errors import CoachConfigurationError, CoachEvidenceError
from gym_coach.coach.schemas import (
    AthleteProfileView,
    CoachContext,
    CoachResponse,
    EvidenceFact,
    ProposedExercise,
    ProposedSet,
    ProposedWorkout,
)
from gym_coach.coach.service import CoachService


def _context() -> CoachContext:
    return CoachContext(
        profile=AthleteProfileView(
            id=uuid4(),
            experience_level="intermediate",
            training_days_per_week=4,
            session_duration_minutes=60,
            equipment=["barbell"],
            limitations=[],
            preferences=[],
        ),
        goals=[],
        routines=[],
        evidence=[
            EvidenceFact(
                id="metric.workouts.28d",
                category="metric",
                description="Completed workouts",
                value="8",
                unit="sessions",
            )
        ],
    )


class ContextCoachService(CoachService):
    async def _build_context(self, *, as_of: datetime) -> CoachContext:
        del as_of
        return _context()


def _service(output: dict[str, object]) -> ContextCoachService:
    unused_factory = cast(async_sessionmaker[AsyncSession], object())
    return ContextCoachService(
        unused_factory,
        model=TestModel(custom_output_args=output),
        model_name="test",
    )


@pytest.mark.asyncio
async def test_coach_accepts_structured_evidence_based_analysis_without_network() -> None:
    service = _service(
        {
            "answer": "La frecuencia observada es compatible con el objetivo.",
            "evidence_ids": ["metric.workouts.28d"],
            "findings": [
                {
                    "statement": "Se completaron ocho sesiones.",
                    "evidence_ids": ["metric.workouts.28d"],
                }
            ],
            "proposal": None,
        }
    )

    result = await service.ask("Revisa mi entrenamiento", as_of=datetime.now(UTC))

    assert result.response.findings[0].evidence_ids == ["metric.workouts.28d"]
    assert result.stored_proposal is None


@pytest.mark.asyncio
async def test_coach_rejects_unknown_evidence_reference() -> None:
    service = _service(
        {
            "answer": "Invented conclusion",
            "evidence_ids": ["metric.unknown"],
            "findings": [{"statement": "Invented", "evidence_ids": ["metric.unknown"]}],
            "proposal": None,
        }
    )

    with pytest.raises(CoachEvidenceError, match=r"metric\.unknown"):
        await service.ask("Review", as_of=datetime.now(UTC))


@pytest.mark.asyncio
async def test_coach_maps_invalid_structured_output_to_safe_error() -> None:
    service = _service(
        {
            "answer": "",
            "evidence_ids": ["metric.workouts.28d"],
            "findings": [],
            "proposal": None,
        }
    )

    with pytest.raises(CoachConfigurationError, match="valid response"):
        await service.ask("Review", as_of=datetime.now(UTC))


def test_proposed_set_rejects_inverted_repetition_range() -> None:
    with pytest.raises(ValidationError, match="reps_max"):
        ProposedSet(reps_min=12, reps_max=8)


def test_superset_groups_require_two_contiguous_exercises() -> None:
    base = {
        "title": "Paired work",
        "rest_seconds": 60,
        "sets": [{"reps_min": 8, "reps_max": 12}],
    }
    workout = ProposedWorkout(
        title="Upper",
        exercises=[
            ProposedExercise(**base, superset_group="push_pull"),
            ProposedExercise(**base, superset_group="push_pull"),
        ],
    )
    assert workout.exercises[0].superset_group == "push_pull"

    with pytest.raises(ValidationError, match="at least two"):
        ProposedWorkout(
            title="Invalid",
            exercises=[ProposedExercise(**base, superset_group="alone")],
        )

    with pytest.raises(ValidationError, match="contiguous"):
        ProposedWorkout(
            title="Invalid",
            exercises=[
                ProposedExercise(**base, superset_group="a"),
                ProposedExercise(**base),
                ProposedExercise(**base, superset_group="a"),
            ],
        )


def test_coach_response_rejects_additional_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        CoachResponse.model_validate(
            {
                "answer": "ok",
                "evidence_ids": ["metric.workouts.28d"],
                "findings": [],
                "secret": "no",
            }
        )
