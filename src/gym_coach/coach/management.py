from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gym_coach.coach.errors import (
    CoachConfigurationError,
    CoachPersistenceError,
)
from gym_coach.coach.schemas import (
    AthleteProfileInput,
    AthleteProfileView,
    StoredProposalView,
    TrainingGoalInput,
    TrainingGoalView,
)
from gym_coach.persistence.coach_repository import CoachRepository


class CoachManagementService:
    """Manage structured coach state without requiring an LLM runtime."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def set_profile(self, data: AthleteProfileInput) -> AthleteProfileView:
        try:
            async with self._session_factory.begin() as session:
                return await CoachRepository(session).upsert_profile(data)
        except SQLAlchemyError as exc:
            raise CoachPersistenceError("Could not save athlete profile in PostgreSQL") from exc

    async def add_goal(self, data: TrainingGoalInput) -> TrainingGoalView:
        try:
            async with self._session_factory.begin() as session:
                repository = CoachRepository(session)
                profile = await repository.get_profile()
                if profile is None:
                    raise CoachConfigurationError(
                        "Configure the athlete profile before adding goals"
                    )
                return await repository.add_goal(profile.id, data)
        except SQLAlchemyError as exc:
            raise CoachPersistenceError("Could not save training goal in PostgreSQL") from exc

    async def list_proposals(self) -> list[StoredProposalView]:
        try:
            async with self._session_factory() as session:
                return await CoachRepository(session).list_proposals()
        except SQLAlchemyError as exc:
            raise CoachPersistenceError("Could not load coach proposals from PostgreSQL") from exc

    async def decide(self, proposal_id: UUID, status: str) -> StoredProposalView:
        if status not in {"approved", "rejected"}:
            raise ValueError("Proposal status must be approved or rejected")
        try:
            async with self._session_factory.begin() as session:
                result = await CoachRepository(session).decide_proposal(proposal_id, status)
                if result is None:
                    raise CoachConfigurationError("Coach proposal was not found")
                return result
        except SQLAlchemyError as exc:
            raise CoachPersistenceError("Could not update coach proposal in PostgreSQL") from exc
