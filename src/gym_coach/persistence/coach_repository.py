from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from gym_coach.coach.schemas import (
    AthleteProfileInput,
    AthleteProfileView,
    CoachProposalOutput,
    EvidenceFact,
    RoutineContext,
    RoutineExerciseContext,
    RoutineSetContext,
    StoredProposalView,
    TrainingGoalInput,
    TrainingGoalView,
)
from gym_coach.persistence.models import (
    AthleteProfile,
    AthleteProfileVersion,
    CoachProposal,
    Routine,
    RoutineExercise,
    TrainingGoal,
)


class CoachRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_profile(
        self,
        data: AthleteProfileInput,
        *,
        source: str = "cli",
        user_confirmed: bool = True,
    ) -> AthleteProfileView:
        profile = await self._session.scalar(
            select(AthleteProfile).where(AthleteProfile.profile_key == "default").with_for_update()
        )
        if profile is None:
            profile = AthleteProfile(profile_key="default", version=1)
            self._session.add(profile)
        else:
            profile.version += 1
        for key, value in data.model_dump().items():
            setattr(profile, key, value)
        await self._session.flush()
        self._session.add(
            AthleteProfileVersion(
                profile_id=profile.id,
                version=profile.version,
                profile_data=data.model_dump(mode="json"),
                source=source,
                user_confirmed=user_confirmed,
            )
        )
        await self._session.flush()
        return self._profile_view(profile)

    async def get_profile(self) -> AthleteProfileView | None:
        profile = await self._session.scalar(
            select(AthleteProfile).where(AthleteProfile.profile_key == "default")
        )
        return None if profile is None else self._profile_view(profile)

    async def add_goal(
        self,
        profile_id: UUID,
        data: TrainingGoalInput,
        *,
        source: str = "cli",
        user_confirmed: bool = True,
        supersedes_id: UUID | None = None,
    ) -> TrainingGoalView:
        await self._session.scalar(
            select(AthleteProfile.id).where(AthleteProfile.id == profile_id).with_for_update()
        )
        current_version = await self._session.scalar(
            select(func.coalesce(func.max(TrainingGoal.version), 0)).where(
                TrainingGoal.profile_id == profile_id
            )
        )
        version = (current_version or 0) + 1
        goal = TrainingGoal(
            profile_id=profile_id,
            version=version,
            goal_type=data.goal_type,
            description=data.description,
            priority=data.priority,
            target_date=(
                datetime.combine(data.target_date, datetime.min.time(), tzinfo=UTC)
                if data.target_date
                else None
            ),
            status="active",
            source=source,
            user_confirmed=user_confirmed,
            supersedes_id=supersedes_id,
        )
        self._session.add(goal)
        await self._session.flush()
        return self._goal_view(goal)

    async def revise_goal(
        self,
        profile_id: UUID,
        goal_version: int,
        data: TrainingGoalInput,
        *,
        source: str,
        user_confirmed: bool,
    ) -> TrainingGoalView | None:
        await self._session.scalar(
            select(AthleteProfile.id).where(AthleteProfile.id == profile_id).with_for_update()
        )
        current = await self._session.scalar(
            select(TrainingGoal)
            .where(
                TrainingGoal.profile_id == profile_id,
                TrainingGoal.version == goal_version,
                TrainingGoal.status == "active",
            )
            .with_for_update()
        )
        if current is None:
            return None
        current.status = "archived"
        return await self.add_goal(
            profile_id,
            data,
            source=source,
            user_confirmed=user_confirmed,
            supersedes_id=current.id,
        )

    async def active_goals(self, profile_id: UUID) -> list[TrainingGoalView]:
        goals = (
            await self._session.scalars(
                select(TrainingGoal)
                .where(TrainingGoal.profile_id == profile_id, TrainingGoal.status == "active")
                .order_by(TrainingGoal.priority, TrainingGoal.version)
            )
        ).all()
        return [self._goal_view(item) for item in goals]

    async def active_routines(self) -> list[RoutineContext]:
        routines = (
            await self._session.scalars(
                select(Routine)
                .where(Routine.deleted_at.is_(None))
                .options(selectinload(Routine.exercises).selectinload(RoutineExercise.sets))
                .order_by(Routine.title)
            )
        ).all()
        return [
            RoutineContext(
                routine_id=routine.external_id,
                title=routine.title,
                exercises=[
                    RoutineExerciseContext(
                        exercise_template_id=exercise.exercise_template_external_id,
                        title=exercise.title,
                        rest_seconds=exercise.rest_seconds,
                        sets=[
                            RoutineSetContext(
                                set_type=item.set_type,
                                weight_kg=str(item.weight_kg)
                                if item.weight_kg is not None
                                else None,
                                reps=item.reps,
                                rep_range_start=item.rep_range_start,
                                rep_range_end=item.rep_range_end,
                            )
                            for item in exercise.sets
                        ],
                    )
                    for exercise in routine.exercises
                ],
            )
            for routine in routines
        ]

    async def save_proposal(
        self,
        *,
        profile_id: UUID,
        proposal: CoachProposalOutput,
        evidence: list[EvidenceFact],
        model_name: str,
        request_source: str = "pydanticai",
        user_requested: bool = False,
    ) -> StoredProposalView:
        row = CoachProposal(
            profile_id=profile_id,
            kind=proposal.kind,
            status="draft",
            title=proposal.title,
            summary=proposal.summary,
            proposal_data=proposal.model_dump(mode="json"),
            evidence_data=[item.model_dump(mode="json") for item in evidence],
            model_name=model_name,
            request_source=request_source,
            user_requested=user_requested,
        )
        self._session.add(row)
        await self._session.flush()
        return self._proposal_view(row)

    async def list_proposals(self) -> list[StoredProposalView]:
        rows = (
            await self._session.scalars(
                select(CoachProposal).order_by(CoachProposal.created_at.desc())
            )
        ).all()
        return [self._proposal_view(item) for item in rows]

    async def get_proposal(
        self, proposal_id: UUID
    ) -> tuple[StoredProposalView, CoachProposalOutput] | None:
        row = await self._session.get(CoachProposal, proposal_id)
        if row is None:
            return None
        return self._proposal_view(row), CoachProposalOutput.model_validate(row.proposal_data)

    async def decide_proposal(
        self,
        proposal_id: UUID,
        status: str,
        *,
        decision_source: str = "cli",
        user_confirmed: bool = True,
    ) -> StoredProposalView | None:
        row = await self._session.get(CoachProposal, proposal_id)
        if row is None:
            return None
        if row.status != "draft":
            raise ValueError("Only draft proposals can be approved or rejected")
        row.status = status
        row.decided_at = datetime.now(UTC)
        row.decision_source = decision_source
        row.decision_user_confirmed = user_confirmed
        await self._session.flush()
        return self._proposal_view(row)

    @staticmethod
    def _profile_view(row: AthleteProfile) -> AthleteProfileView:
        return AthleteProfileView.model_validate(
            {
                "id": row.id,
                "version": row.version,
                "experience_level": row.experience_level,
                "training_days_per_week": row.training_days_per_week,
                "session_duration_minutes": row.session_duration_minutes,
                "equipment": row.equipment,
                "limitations": row.limitations,
                "preferences": row.preferences,
                "limitations_reviewed": row.limitations_reviewed,
                "preferences_reviewed": row.preferences_reviewed,
            }
        )

    @staticmethod
    def _goal_view(row: TrainingGoal) -> TrainingGoalView:
        return TrainingGoalView.model_validate(
            {
                "id": row.id,
                "version": row.version,
                "goal_type": row.goal_type,
                "description": row.description,
                "priority": row.priority,
                "target_date": row.target_date.date() if row.target_date else None,
                "status": row.status,
            }
        )

    @staticmethod
    def _proposal_view(row: CoachProposal) -> StoredProposalView:
        return StoredProposalView.model_validate(
            {
                "id": row.id,
                "kind": row.kind,
                "status": row.status,
                "title": row.title,
                "summary": row.summary,
                "model_name": row.model_name,
                "created_at": row.created_at,
                "decided_at": row.decided_at,
            }
        )
