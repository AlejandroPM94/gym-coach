from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from gym_coach.coach.schemas import (
    AthleteProfileInput,
    CoachProposalOutput,
    EvidenceFact,
    ProposedExercise,
    ProposedSet,
    ProposedWorkout,
    TrainingGoalInput,
)
from gym_coach.coach.schemas import (
    PlanChangeJustification as CoachPlanChangeJustification,
)
from gym_coach.mcp.schemas import (
    AthleteGoal,
    AthleteProfileUpdate,
    AthleteSummary,
    CompletedExercise,
    CompletedSet,
    ExercisePlanChange,
    ExerciseTemplateSearchResults,
    ExerciseTemplateSummary,
    GoalMutationResult,
    MuscleGroupPlanChange,
    OnboardingStatus,
    PlanComparisonSide,
    PlanDecisionResult,
    PlannedExercise,
    PlannedSet,
    ProfileMutationResult,
    ProposedPlanWorkout,
    RecentWorkouts,
    RoutineList,
    RoutineSummary,
    TrainingGoalUpdate,
    TrainingPlanComparison,
    TrainingPlanProposal,
    TrainingPlanProposalInput,
    TrainingRoutine,
    TrainingWorkout,
    VerifiedPlanEvidence,
    WorkoutSummary,
)
from gym_coach.persistence.coach_repository import CoachRepository
from gym_coach.persistence.models import (
    AthleteProfile,
    ExerciseTemplate,
    HevyUser,
    Routine,
    RoutineExercise,
    TrainingGoal,
    Workout,
    WorkoutExercise,
)


class PostgresMCPRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def is_available(self) -> bool:
        async with self._session_factory() as session:
            await session.execute(select(1))
        return True

    async def athlete_summary(self) -> AthleteSummary:
        async with self._session_factory() as session:
            profile = await session.scalar(
                select(AthleteProfile).where(AthleteProfile.profile_key == "default")
            )
            hevy_available = bool(
                await session.scalar(
                    select(func.count()).select_from(HevyUser).where(HevyUser.deleted_at.is_(None))
                )
            )
            if profile is None:
                return AthleteSummary(
                    source="hevy_sync" if hevy_available else "none",
                    profile_complete=False,
                    hevy_data_available=hevy_available,
                    pending_fields=[
                        "experience_level",
                        "training_days_per_week",
                        "session_duration_minutes",
                        "equipment",
                        "limitations_reviewed",
                        "preferences_reviewed",
                        "goals",
                    ],
                )
            goals = (
                await session.scalars(
                    select(TrainingGoal)
                    .where(TrainingGoal.profile_id == profile.id, TrainingGoal.status == "active")
                    .order_by(TrainingGoal.priority, TrainingGoal.version)
                )
            ).all()
            pending = []
            if profile.session_duration_minutes is None:
                pending.append("session_duration_minutes")
            if not profile.equipment:
                pending.append("equipment")
            if not profile.limitations_reviewed:
                pending.append("limitations_reviewed")
            if not profile.preferences_reviewed:
                pending.append("preferences_reviewed")
            if not goals:
                pending.append("goals")
            return AthleteSummary(
                source="athlete_profile",
                profile_complete=not pending,
                profile_version=profile.version,
                profile_evidence_id=f"profile:{profile.version}",
                hevy_data_available=hevy_available,
                experience_level=profile.experience_level,
                training_days_per_week=profile.training_days_per_week,
                session_duration_minutes=profile.session_duration_minutes,
                equipment=profile.equipment,
                limitations=profile.limitations,
                preferences=profile.preferences,
                limitations_reviewed=profile.limitations_reviewed,
                preferences_reviewed=profile.preferences_reviewed,
                goals=[
                    AthleteGoal(
                        evidence_id=f"goal:{goal.version}",
                        version=goal.version,
                        goal_type=goal.goal_type,
                        description=goal.description,
                        priority=goal.priority,
                        target_date=goal.target_date.date() if goal.target_date else None,
                    )
                    for goal in goals
                ],
                pending_fields=pending,
            )

    async def onboarding_status(self) -> OnboardingStatus:
        summary = await self.athlete_summary()
        pending = list(summary.pending_fields)
        if not summary.goals and "goals" not in pending:
            pending.append("goals")
        ready = summary.profile_complete and bool(summary.goals)
        if summary.source != "athlete_profile":
            next_action = (
                "Ask the athlete for the missing profile fields, then request confirmation."
            )
        elif not summary.goals:
            next_action = (
                "Ask for at least one training goal, summarize it, then request confirmation."
            )
        elif pending:
            next_action = "Complete the remaining fields and request confirmation before saving."
        else:
            next_action = "The structured onboarding is complete; training analysis may begin."
        return OnboardingStatus(
            profile_present=summary.source == "athlete_profile",
            profile_version=summary.profile_version,
            active_goal_count=len(summary.goals),
            pending_fields=pending,
            ready_for_training_analysis=ready,
            next_action=next_action,
        )

    async def save_profile(self, data: AthleteProfileUpdate) -> ProfileMutationResult:
        async with self._session_factory.begin() as session:
            profile = await CoachRepository(session).upsert_profile(
                AthleteProfileInput.model_validate(data.model_dump()),
                source="hermes_mcp",
                user_confirmed=True,
            )
        return ProfileMutationResult(
            profile_version=profile.version,
            message="Confirmed athlete profile saved in PostgreSQL.",
        )

    async def add_goal(self, data: TrainingGoalUpdate) -> GoalMutationResult | None:
        async with self._session_factory.begin() as session:
            repository = CoachRepository(session)
            profile = await repository.get_profile()
            if profile is None:
                return None
            goal = await repository.add_goal(
                profile.id,
                TrainingGoalInput.model_validate(data.model_dump()),
                source="hermes_mcp",
                user_confirmed=True,
            )
        return GoalMutationResult(
            goal_version=goal.version,
            message="Confirmed training goal saved in PostgreSQL.",
        )

    async def revise_goal(
        self, goal_version: int, data: TrainingGoalUpdate
    ) -> GoalMutationResult | None:
        async with self._session_factory.begin() as session:
            repository = CoachRepository(session)
            profile = await repository.get_profile()
            if profile is None:
                return None
            goal = await repository.revise_goal(
                profile.id,
                goal_version,
                TrainingGoalInput.model_validate(data.model_dump()),
                source="hermes_mcp",
                user_confirmed=True,
            )
        if goal is None:
            return None
        return GoalMutationResult(
            goal_version=goal.version,
            message=(
                f"Confirmed goal revision saved as version {goal.version}; "
                f"version {goal_version} was archived."
            ),
        )

    async def list_routines(self) -> RoutineList:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(Routine)
                    .where(Routine.deleted_at.is_(None))
                    .options(selectinload(Routine.exercises))
                    .order_by(Routine.folder_id.asc().nulls_last(), Routine.title)
                )
            ).all()
        routines = [
            RoutineSummary(
                evidence_id=f"routine:{row.external_id}",
                external_id=row.external_id,
                title=row.title,
                folder_id=row.folder_id,
                position=index,
                exercise_count=len(row.exercises),
            )
            for index, row in enumerate(rows, start=1)
        ]
        return RoutineList(count=len(routines), routines=routines)

    async def get_routine(self, external_id: str) -> TrainingRoutine | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(Routine)
                .where(Routine.external_id == external_id, Routine.deleted_at.is_(None))
                .options(selectinload(Routine.exercises).selectinload(RoutineExercise.sets))
            )
        if row is None:
            return None
        return TrainingRoutine(
            external_id=row.external_id,
            title=row.title,
            folder_id=row.folder_id,
            updated_at=row.source_updated_at,
            exercises=[
                PlannedExercise(
                    position=exercise.position + 1,
                    exercise_template_external_id=exercise.exercise_template_external_id,
                    title=exercise.title,
                    notes=exercise.notes,
                    rest_seconds=exercise.rest_seconds,
                    superset_id=exercise.superset_id,
                    sets=[
                        PlannedSet(
                            position=item.position + 1,
                            set_type=item.set_type,
                            weight_kg=str(item.weight_kg) if item.weight_kg is not None else None,
                            reps=item.reps,
                            rep_range_start=item.rep_range_start,
                            rep_range_end=item.rep_range_end,
                            distance_meters=(
                                str(item.distance_meters)
                                if item.distance_meters is not None
                                else None
                            ),
                            duration_seconds=item.duration_seconds,
                        )
                        for item in exercise.sets
                    ],
                )
                for exercise in row.exercises
            ],
        )

    async def recent_workouts(self, limit: int) -> RecentWorkouts:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(Workout)
                    .where(Workout.deleted_at.is_(None))
                    .options(selectinload(Workout.exercises))
                    .order_by(Workout.start_time.desc())
                    .limit(limit)
                )
            ).all()
        workouts = [
            WorkoutSummary(
                external_id=row.external_id,
                title=row.title,
                start_time=row.start_time,
                end_time=row.end_time,
                routine_external_id=row.routine_external_id,
                exercise_count=len(row.exercises),
            )
            for row in rows
        ]
        return RecentWorkouts(requested_limit=limit, count=len(workouts), workouts=workouts)

    async def get_workout(self, external_id: str) -> TrainingWorkout | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(Workout)
                .where(Workout.external_id == external_id, Workout.deleted_at.is_(None))
                .options(selectinload(Workout.exercises).selectinload(WorkoutExercise.sets))
            )
        if row is None:
            return None
        return TrainingWorkout(
            external_id=row.external_id,
            title=row.title,
            description=row.description,
            routine_external_id=row.routine_external_id,
            start_time=row.start_time,
            end_time=row.end_time,
            exercises=[
                CompletedExercise(
                    position=exercise.position + 1,
                    exercise_template_external_id=exercise.exercise_template_external_id,
                    title=exercise.title,
                    notes=exercise.notes,
                    superset_id=exercise.superset_id,
                    sets=[
                        CompletedSet(
                            position=item.position + 1,
                            set_type=item.set_type,
                            weight_kg=str(item.weight_kg) if item.weight_kg is not None else None,
                            reps=item.reps,
                            distance_meters=(
                                str(item.distance_meters)
                                if item.distance_meters is not None
                                else None
                            ),
                            duration_seconds=item.duration_seconds,
                            rpe=item.rpe,
                        )
                        for item in exercise.sets
                    ],
                )
                for exercise in row.exercises
            ],
        )

    async def search_exercise_templates(
        self, query: str, limit: int
    ) -> ExerciseTemplateSearchResults:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(ExerciseTemplate)
                    .where(
                        ExerciseTemplate.deleted_at.is_(None),
                        func.lower(ExerciseTemplate.title).contains(query.lower(), autoescape=True),
                    )
                    .options(selectinload(ExerciseTemplate.secondary_muscles))
                    .order_by(ExerciseTemplate.title)
                    .limit(limit)
                )
            ).all()
        results = [
            ExerciseTemplateSummary(
                external_id=row.external_id,
                title=row.title,
                exercise_type=row.exercise_type,
                primary_muscle_group=row.primary_muscle_group,
                secondary_muscle_groups=[item.muscle_group for item in row.secondary_muscles],
                equipment=row.equipment,
                is_custom=row.is_custom,
            )
            for row in rows
        ]
        return ExerciseTemplateSearchResults(
            query=query, requested_limit=limit, count=len(results), results=results
        )

    async def exercise_template_exists(self, external_id: str) -> bool:
        async with self._session_factory() as session:
            return bool(
                await session.scalar(
                    select(func.count())
                    .select_from(ExerciseTemplate)
                    .where(
                        ExerciseTemplate.external_id == external_id,
                        ExerciseTemplate.deleted_at.is_(None),
                    )
                )
            )

    async def create_plan_proposal(
        self, data: TrainingPlanProposalInput, evidence: list[VerifiedPlanEvidence]
    ) -> TrainingPlanProposal | None:
        await self._validate_plan_references(data)
        internal = _to_coach_proposal(data)
        stored_evidence = [
            EvidenceFact(
                id=item.evidence_id,
                category=item.category,
                description=item.description,
                value=item.value,
                period_start=item.period_start,
                period_end=item.period_end,
            )
            for item in evidence
        ]
        async with self._session_factory.begin() as session:
            repository = CoachRepository(session)
            profile = await repository.get_profile()
            if profile is None:
                return None
            stored = await repository.save_proposal(
                profile_id=profile.id,
                proposal=internal,
                evidence=stored_evidence,
                model_name="hermes:mcp",
                request_source="hermes_mcp",
                user_requested=True,
            )
        return TrainingPlanProposal(
            proposal_id=stored.id,
            status=stored.status,
            created_at=stored.created_at,
            decided_at=stored.decided_at,
            plan=data,
        )

    async def get_plan_proposal(self, proposal_id: UUID) -> TrainingPlanProposal | None:
        async with self._session_factory() as session:
            result = await CoachRepository(session).get_proposal(proposal_id)
        if result is None:
            return None
        stored, proposal = result
        return TrainingPlanProposal(
            proposal_id=stored.id,
            status=stored.status,
            created_at=stored.created_at,
            decided_at=stored.decided_at,
            plan=_to_public_plan(proposal),
        )

    async def compare_plan_proposal(self, proposal_id: UUID) -> TrainingPlanComparison | None:
        proposal = await self.get_plan_proposal(proposal_id)
        if proposal is None:
            return None
        current_routines: list[TrainingRoutine] = []
        source_id = proposal.plan.source_routine_id
        if source_id is not None:
            routine = await self.get_routine(source_id)
            if routine is not None:
                current_routines.append(routine)
        else:
            listed = await self.list_routines()
            for summary in listed.routines:
                routine = await self.get_routine(summary.external_id)
                if routine is not None:
                    current_routines.append(routine)
        current = PlanComparisonSide(
            title=(
                current_routines[0].title
                if len(current_routines) == 1
                else "All active training routines"
            ),
            workout_count=len(current_routines),
            required_workout_count=len(current_routines),
            optional_workout_count=0,
            exercise_count=sum(len(routine.exercises) for routine in current_routines),
            set_count=sum(
                len(exercise.sets) for routine in current_routines for exercise in routine.exercises
            ),
        )
        proposed = PlanComparisonSide(
            title=proposal.plan.title,
            workout_count=len(proposal.plan.workouts),
            required_workout_count=sum(not workout.optional for workout in proposal.plan.workouts),
            optional_workout_count=sum(workout.optional for workout in proposal.plan.workouts),
            exercise_count=sum(len(workout.exercises) for workout in proposal.plan.workouts),
            set_count=sum(
                len(exercise.sets)
                for workout in proposal.plan.workouts
                for exercise in workout.exercises
            ),
        )
        current_exercises = _aggregate_current_exercises(current_routines)
        proposed_exercises, unmatched_proposed = _aggregate_proposed_exercises(
            proposal.plan.workouts
        )
        template_ids = set(current_exercises) | set(proposed_exercises)
        muscle_groups = await self._exercise_muscle_groups(template_ids)
        exercise_changes = [
            ExercisePlanChange(
                exercise_template_external_id=template_id,
                title=(proposed_exercises.get(template_id) or current_exercises[template_id]).title,
                change=(
                    "retained"
                    if template_id in current_exercises and template_id in proposed_exercises
                    else "added"
                    if template_id in proposed_exercises
                    else "removed"
                ),
                current_frequency=current_exercises.get(template_id, _EMPTY_AGGREGATE).frequency,
                proposed_frequency=proposed_exercises.get(template_id, _EMPTY_AGGREGATE).frequency,
                current_sets=current_exercises.get(template_id, _EMPTY_AGGREGATE).sets,
                proposed_sets=proposed_exercises.get(template_id, _EMPTY_AGGREGATE).sets,
                set_delta=(
                    proposed_exercises.get(template_id, _EMPTY_AGGREGATE).sets
                    - current_exercises.get(template_id, _EMPTY_AGGREGATE).sets
                ),
            )
            for template_id in sorted(template_ids)
        ]
        current_muscles = _aggregate_muscle_sets(current_exercises, muscle_groups)
        proposed_muscles = _aggregate_muscle_sets(proposed_exercises, muscle_groups)
        muscle_group_changes = [
            MuscleGroupPlanChange(
                muscle_group=muscle_group,
                current_sets=current_muscles.get(muscle_group, 0),
                proposed_sets=proposed_muscles.get(muscle_group, 0),
                set_delta=(
                    proposed_muscles.get(muscle_group, 0) - current_muscles.get(muscle_group, 0)
                ),
            )
            for muscle_group in sorted(set(current_muscles) | set(proposed_muscles))
        ]
        return TrainingPlanComparison(
            proposal_id=proposal.proposal_id,
            status=proposal.status,
            current=current,
            proposed=proposed,
            rationale=proposal.plan.rationale,
            exercise_changes=exercise_changes,
            muscle_group_changes=muscle_group_changes,
            unmatched_current_titles=[],
            unmatched_proposed_titles=unmatched_proposed,
        )

    async def decide_plan_proposal(
        self, proposal_id: UUID, decision: Literal["approved", "rejected"]
    ) -> PlanDecisionResult | None:
        async with self._session_factory.begin() as session:
            stored = await CoachRepository(session).decide_proposal(
                proposal_id,
                decision,
                decision_source="hermes_mcp",
                user_confirmed=True,
            )
        if stored is None:
            return None
        return PlanDecisionResult(
            proposal_id=stored.id,
            status=decision,
            message=(f"Proposal marked {decision} in PostgreSQL. No routine was modified in Hevy."),
        )

    async def _validate_plan_references(self, data: TrainingPlanProposalInput) -> None:
        async with self._session_factory() as session:
            if data.source_routine_id is not None:
                routine_exists = await session.scalar(
                    select(func.count())
                    .select_from(Routine)
                    .where(
                        Routine.external_id == data.source_routine_id,
                        Routine.deleted_at.is_(None),
                    )
                )
                if not routine_exists:
                    raise ValueError("source_routine_id does not identify an active routine")
            referenced_templates = {
                exercise.exercise_template_external_id
                for workout in data.workouts
                for exercise in workout.exercises
                if exercise.exercise_template_external_id is not None
            }
            if referenced_templates:
                known_templates = set(
                    await session.scalars(
                        select(ExerciseTemplate.external_id).where(
                            ExerciseTemplate.external_id.in_(referenced_templates),
                            ExerciseTemplate.deleted_at.is_(None),
                        )
                    )
                )
                unknown = referenced_templates - known_templates
                if unknown:
                    raise ValueError("proposal references unknown or inactive exercise templates")

    async def _exercise_muscle_groups(self, external_ids: set[str]) -> dict[str, str]:
        if not external_ids:
            return {}
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        ExerciseTemplate.external_id,
                        ExerciseTemplate.primary_muscle_group,
                    ).where(ExerciseTemplate.external_id.in_(external_ids))
                )
            ).all()
        return {external_id: muscle_group for external_id, muscle_group in rows}


def _to_coach_proposal(data: TrainingPlanProposalInput) -> CoachProposalOutput:
    return CoachProposalOutput(
        kind=data.kind,
        title=data.title,
        summary=data.summary,
        rationale=data.rationale,
        evidence_ids=data.evidence_ids,
        source_routine_id=data.source_routine_id,
        workouts=[
            ProposedWorkout(
                title=workout.title,
                optional=workout.optional,
                location=workout.location,
                estimated_duration_minutes=workout.estimated_duration_minutes,
                exercises=[
                    ProposedExercise(
                        exercise_template_id=exercise.exercise_template_external_id,
                        title=exercise.title,
                        rest_seconds=exercise.rest_seconds,
                        sets=[
                            ProposedSet.model_validate(item.model_dump()) for item in exercise.sets
                        ],
                        notes=exercise.notes,
                    )
                    for exercise in workout.exercises
                ],
            )
            for workout in data.workouts
        ],
        changes=[
            CoachPlanChangeJustification.model_validate(change.model_dump())
            for change in data.changes
        ],
    )


def _to_public_plan(data: CoachProposalOutput) -> TrainingPlanProposalInput:
    return TrainingPlanProposalInput.model_validate(
        {
            **data.model_dump(mode="json", exclude={"workouts"}),
            "workouts": [
                {
                    "title": workout.title,
                    "optional": workout.optional,
                    "location": workout.location,
                    "estimated_duration_minutes": workout.estimated_duration_minutes,
                    "exercises": [
                        {
                            "exercise_template_external_id": exercise.exercise_template_id,
                            "title": exercise.title,
                            "rest_seconds": exercise.rest_seconds,
                            "sets": [item.model_dump(mode="json") for item in exercise.sets],
                            "notes": exercise.notes,
                        }
                        for exercise in workout.exercises
                    ],
                }
                for workout in data.workouts
            ],
        }
    )


@dataclass(frozen=True, slots=True)
class _ExerciseAggregate:
    title: str
    frequency: int
    sets: int


_EMPTY_AGGREGATE = _ExerciseAggregate(title="", frequency=0, sets=0)


def _aggregate_current_exercises(
    routines: list[TrainingRoutine],
) -> dict[str, _ExerciseAggregate]:
    result: dict[str, _ExerciseAggregate] = {}
    for routine in routines:
        for exercise in routine.exercises:
            current = result.get(
                exercise.exercise_template_external_id,
                _ExerciseAggregate(title=exercise.title, frequency=0, sets=0),
            )
            result[exercise.exercise_template_external_id] = _ExerciseAggregate(
                title=exercise.title,
                frequency=current.frequency + 1,
                sets=current.sets + len(exercise.sets),
            )
    return result


def _aggregate_proposed_exercises(
    workouts: list[ProposedPlanWorkout],
) -> tuple[dict[str, _ExerciseAggregate], list[str]]:
    result: dict[str, _ExerciseAggregate] = {}
    unmatched: list[str] = []
    for workout in workouts:
        for exercise in workout.exercises:
            template_id = exercise.exercise_template_external_id
            if template_id is None:
                unmatched.append(exercise.title)
                continue
            current = result.get(
                template_id,
                _ExerciseAggregate(title=exercise.title, frequency=0, sets=0),
            )
            result[template_id] = _ExerciseAggregate(
                title=exercise.title,
                frequency=current.frequency + 1,
                sets=current.sets + len(exercise.sets),
            )
    return result, unmatched


def _aggregate_muscle_sets(
    exercises: dict[str, _ExerciseAggregate], muscle_groups: dict[str, str]
) -> dict[str, int]:
    result: dict[str, int] = {}
    for template_id, exercise in exercises.items():
        muscle_group = muscle_groups.get(template_id)
        if muscle_group is not None:
            result[muscle_group] = result.get(muscle_group, 0) + exercise.sets
    return result
