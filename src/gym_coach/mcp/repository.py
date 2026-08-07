import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from gym_coach.automation.repository import AutomationRepository
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
from gym_coach.coaching.assessment import (
    COACHING_RULES,
    HistoryFacts,
    assess_training_history,
    calculate_bmi,
    calculate_mifflin_st_jeor,
    protein_range,
)
from gym_coach.mcp.schemas import (
    AthleteCheckInInput,
    AthleteCheckInView,
    AthleteGoal,
    AthleteMeasurementInput,
    AthleteMeasurementView,
    AthleteProfileUpdate,
    AthleteSummary,
    CoachingAssessment,
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
    RoutineApplicationCommand,
    RoutineApplicationPreview,
    RoutineApplicationReconciliationContext,
    RoutineList,
    RoutineSummary,
    TrainingGoalUpdate,
    TrainingHistoryAssessment,
    TrainingPlanComparison,
    TrainingPlanProposal,
    TrainingPlanProposalInput,
    TrainingRoutine,
    TrainingWorkout,
    VerifiedPlanEvidence,
    WorkoutReviewAcknowledgement,
    WorkoutSummary,
)
from gym_coach.persistence.coach_repository import CoachRepository
from gym_coach.persistence.models import (
    AthleteCheckIn,
    AthleteMeasurement,
    AthleteProfile,
    CoachProposal,
    ExerciseTemplate,
    HevyUser,
    Routine,
    RoutineApplication,
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
                        "training_days_per_week",
                        "session_duration_minutes",
                        "equipment",
                        "limitations_reviewed",
                        "preferences_reviewed",
                        "birth_year",
                        "height_cm",
                        "current_weight",
                        "lifestyle_reviewed",
                        "nutrition_reviewed",
                        "health_reviewed",
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
            if profile.birth_year is None:
                pending.append("birth_year")
            if profile.height_cm is None:
                pending.append("height_cm")
            if not profile.lifestyle_reviewed:
                pending.append("lifestyle_reviewed")
            if not profile.nutrition_reviewed:
                pending.append("nutrition_reviewed")
            if not profile.health_reviewed:
                pending.append("health_reviewed")
            has_weight = bool(
                await session.scalar(
                    select(func.count())
                    .select_from(AthleteMeasurement)
                    .where(
                        AthleteMeasurement.profile_id == profile.id,
                        AthleteMeasurement.weight_kg.is_not(None),
                    )
                )
            )
            if not has_weight:
                pending.append("current_weight")
            if not goals:
                pending.append("goals")
            return AthleteSummary(
                source="athlete_profile",
                profile_complete=not pending,
                profile_version=profile.version,
                profile_evidence_id=f"profile:{profile.version}",
                hevy_data_available=hevy_available,
                experience_level=profile.experience_level,
                birth_year=profile.birth_year,
                sex_for_energy_equation=profile.sex_for_energy_equation,
                height_cm=str(profile.height_cm) if profile.height_cm is not None else None,
                training_days_per_week=profile.training_days_per_week,
                session_duration_minutes=profile.session_duration_minutes,
                equipment=profile.equipment,
                limitations=profile.limitations,
                preferences=profile.preferences,
                limitations_reviewed=profile.limitations_reviewed,
                preferences_reviewed=profile.preferences_reviewed,
                occupation_activity=profile.occupation_activity,
                average_daily_steps=profile.average_daily_steps,
                sleep_hours=profile.sleep_hours,
                sleep_quality=profile.sleep_quality,
                stress_level=profile.stress_level,
                dietary_pattern=profile.dietary_pattern,
                dietary_restrictions=profile.dietary_restrictions,
                food_allergies=profile.food_allergies,
                nutrition_preferences=profile.nutrition_preferences,
                nutrition_tracking_preference=profile.nutrition_tracking_preference,
                health_conditions=profile.health_conditions,
                medications_affecting_training=profile.medications_affecting_training,
                lifestyle_reviewed=profile.lifestyle_reviewed,
                nutrition_reviewed=profile.nutrition_reviewed,
                health_reviewed=profile.health_reviewed,
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

    async def training_history_assessment(self) -> TrainingHistoryAssessment:
        async with self._session_factory() as session:
            period_start, period_end, workout_count = (
                await session.execute(
                    select(
                        func.min(Workout.start_time),
                        func.max(Workout.start_time),
                        func.count(Workout.id),
                    ).where(Workout.deleted_at.is_(None))
                )
            ).one()
            active_week_count = await session.scalar(
                select(
                    func.count(func.distinct(func.date_trunc("week", Workout.start_time)))
                ).where(Workout.deleted_at.is_(None))
            )
            distinct_exercises = await session.scalar(
                select(func.count(func.distinct(WorkoutExercise.exercise_template_external_id)))
                .join(Workout, Workout.id == WorkoutExercise.workout_id)
                .where(Workout.deleted_at.is_(None))
            )
        return assess_training_history(
            HistoryFacts(
                period_start=period_start,
                period_end=period_end,
                workout_count=workout_count or 0,
                active_week_count=active_week_count or 0,
                distinct_exercise_count=distinct_exercises or 0,
            ),
            as_of=date.today(),
        )

    async def coaching_assessment(self) -> CoachingAssessment:
        history = await self.training_history_assessment()
        async with self._session_factory() as session:
            profile = await session.scalar(
                select(AthleteProfile).where(AthleteProfile.profile_key == "default")
            )
            measurement = None
            goals: list[TrainingGoal] = []
            if profile is not None:
                measurement = await session.scalar(
                    select(AthleteMeasurement)
                    .where(AthleteMeasurement.profile_id == profile.id)
                    .order_by(AthleteMeasurement.measured_on.desc())
                )
                goals = list(
                    await session.scalars(
                        select(TrainingGoal).where(
                            TrainingGoal.profile_id == profile.id,
                            TrainingGoal.status == "active",
                        )
                    )
                )
        missing: list[str] = []
        questions: list[str] = []
        if profile is None:
            missing.append("athlete_profile")
            questions.append("Complete the structured athlete interview.")
        else:
            checks = (
                (profile.birth_year is None, "birth_year", "What is your birth year?"),
                (profile.height_cm is None, "height_cm", "What is your height?"),
                (
                    measurement is None or measurement.weight_kg is None,
                    "weight",
                    "What is your current weight?",
                ),
                (
                    not profile.lifestyle_reviewed,
                    "lifestyle_review",
                    "Review daily activity, sleep and stress.",
                ),
                (
                    not profile.nutrition_reviewed,
                    "nutrition_review",
                    "Review eating pattern, restrictions and tracking preference.",
                ),
                (
                    not profile.health_reviewed,
                    "health_review",
                    "Review health conditions and medications relevant to training or diet.",
                ),
            )
            for absent, field, question in checks:
                if absent:
                    missing.append(field)
                    questions.append(question)
            if not goals:
                missing.append("goals")
                questions.append("Define a measurable primary goal and timeframe.")
        weight = measurement.weight_kg if measurement is not None else None
        bmi = None
        resting_energy = None
        protein = None
        if profile is not None and weight is not None:
            protein = protein_range(weight)
            if profile.height_cm is not None:
                bmi = str(calculate_bmi(weight, profile.height_cm))
            if profile.height_cm is not None and profile.birth_year is not None:
                resting_energy = calculate_mifflin_st_jeor(
                    weight_kg=weight,
                    height_cm=profile.height_cm,
                    age=max(date.today().year - profile.birth_year, 18),
                    sex=profile.sex_for_energy_equation or "unspecified",
                )
        clinical_flags = bool(
            profile is not None
            and (profile.health_conditions or profile.medications_affecting_training)
        )
        goal_types = {goal.goal_type for goal in goals}
        rules = [
            rule
            for rule in COACHING_RULES
            if rule.topic in {"resistance_training", "physical_activity", "diet_quality"}
            or (
                rule.topic in {"fat_loss", "protein"}
                and goal_types & {"fat_loss", "body_recomposition", "hypertrophy"}
            )
        ]
        return CoachingAssessment(
            history=history,
            readiness=(
                "needs_professional_clearance"
                if clinical_flags
                else "needs_interview"
                if missing
                else "ready_for_analysis"
            ),
            missing_or_unreviewed=missing,
            priority_questions=questions,
            latest_weight_kg=str(weight) if weight is not None else None,
            bmi=bmi,
            resting_energy_kcal=resting_energy,
            protein_range_g_per_day=protein,
            nutrition_note=(
                "Fat loss requires nutrition and activity management, not resistance training "
                "alone. Estimate a calorie target only after sufficient confirmed data and "
                "monitor weight trends."
            ),
            safety_note=(
                "This is fitness and general nutrition guidance, not diagnosis or medical "
                "nutrition therapy."
            ),
            applicable_rules=rules,
        )

    async def save_measurement(
        self, data: AthleteMeasurementInput
    ) -> AthleteMeasurementView | None:
        async with self._session_factory.begin() as session:
            profile = await session.scalar(
                select(AthleteProfile).where(AthleteProfile.profile_key == "default")
            )
            if profile is None:
                return None
            existing = await session.scalar(
                select(AthleteMeasurement).where(
                    AthleteMeasurement.profile_id == profile.id,
                    AthleteMeasurement.measured_on == data.measured_on,
                )
            )
            if existing is not None:
                raise ValueError("A measurement already exists for that date")
            row = AthleteMeasurement(
                profile_id=profile.id,
                **data.model_dump(),
                source="hermes_mcp",
                user_confirmed=True,
            )
            session.add(row)
            await session.flush()
            return AthleteMeasurementView(
                measurement_id=row.id,
                **data.model_dump(),
            )

    async def save_check_in(self, data: AthleteCheckInInput) -> AthleteCheckInView | None:
        async with self._session_factory.begin() as session:
            profile = await session.scalar(
                select(AthleteProfile).where(AthleteProfile.profile_key == "default")
            )
            if profile is None:
                return None
            existing = await session.scalar(
                select(AthleteCheckIn).where(
                    AthleteCheckIn.profile_id == profile.id,
                    AthleteCheckIn.checked_on == data.checked_on,
                )
            )
            if existing is not None:
                raise ValueError("A check-in already exists for that date")
            row = AthleteCheckIn(
                profile_id=profile.id,
                **data.model_dump(),
                source="hermes_mcp",
                user_confirmed=True,
            )
            session.add(row)
            await session.flush()
            return AthleteCheckInView(check_in_id=row.id, **data.model_dump())

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
            superset_group_count=len(
                {
                    (routine.external_id, exercise.superset_id)
                    for routine in current_routines
                    for exercise in routine.exercises
                    if exercise.superset_id is not None
                }
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
            superset_group_count=len(
                {
                    (workout_index, exercise.superset_group)
                    for workout_index, workout in enumerate(proposal.plan.workouts)
                    for exercise in workout.exercises
                    if exercise.superset_group is not None
                }
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

    async def prepare_routine_application(
        self, proposal_id: UUID
    ) -> RoutineApplicationPreview | None:
        token = secrets.token_urlsafe(24)
        async with self._session_factory.begin() as session:
            proposal = await session.get(CoachProposal, proposal_id, with_for_update=True)
            if proposal is None:
                return None
            if proposal.status != "approved" or proposal.decision_user_confirmed is not True:
                raise ValueError("The proposal must have a confirmed approval before preparation")
            plan = _to_public_plan(CoachProposalOutput.model_validate(proposal.proposal_data))
            action: Literal["create", "update"] = (
                "create" if plan.kind == "new_routine" else "update"
            )
            source_hash = None
            if action == "update":
                if plan.source_routine_id is None or len(plan.workouts) != 1:
                    raise ValueError(
                        "A Hevy routine update requires one workout and one source_routine_id"
                    )
                source = await session.scalar(
                    select(Routine).where(
                        Routine.external_id == plan.source_routine_id,
                        Routine.deleted_at.is_(None),
                    )
                )
                if source is None:
                    raise ValueError("The source routine is no longer active")
                source_hash = source.content_hash
            _validate_hevy_compatible_plan(plan)
            proposal_hash = _stable_hash(plan.model_dump(mode="json"))
            application = await session.scalar(
                select(RoutineApplication)
                .where(RoutineApplication.proposal_id == proposal_id)
                .with_for_update()
            )
            if application is None:
                application = RoutineApplication(
                    proposal_id=proposal_id,
                    action=action,
                    status="prepared",
                    proposal_hash=proposal_hash,
                    confirmation_token_hash=_token_hash(token),
                    source_routine_hash=source_hash,
                )
                session.add(application)
            elif application.status == "applied":
                raise ValueError("This proposal has already been applied to Hevy")
            elif application.status in {"applying", "partial", "uncertain"}:
                raise ValueError("The previous application outcome must be reconciled first")
            else:
                application.action = action
                application.status = "prepared"
                application.proposal_hash = proposal_hash
                application.confirmation_token_hash = _token_hash(token)
                application.source_routine_hash = source_hash
                application.error_type = None
            await session.flush()
            application_id = application.id
        return RoutineApplicationPreview(
            application_id=application_id,
            proposal_id=proposal_id,
            action=action,
            routine_titles=[workout.title for workout in plan.workouts],
            source_routine_id=plan.source_routine_id,
            confirmation_token=token,
            warning=(
                "This token authorizes one exact external Hevy write. Show this preview and ask "
                "for one final explicit confirmation before applying it."
            ),
        )

    async def claim_routine_application(
        self, proposal_id: UUID, confirmation_token: str
    ) -> RoutineApplicationCommand | None:
        async with self._session_factory.begin() as session:
            application = await session.scalar(
                select(RoutineApplication)
                .where(RoutineApplication.proposal_id == proposal_id)
                .with_for_update()
            )
            if application is None:
                return None
            if application.status != "prepared":
                raise ValueError("The routine application is not in prepared state")
            if not secrets.compare_digest(
                application.confirmation_token_hash, _token_hash(confirmation_token)
            ):
                raise ValueError("The confirmation token is invalid")
            proposal = await session.get(CoachProposal, proposal_id)
            if proposal is None or proposal.status != "approved":
                raise ValueError("The approved proposal is no longer available")
            plan = _to_public_plan(CoachProposalOutput.model_validate(proposal.proposal_data))
            if application.proposal_hash != _stable_hash(plan.model_dump(mode="json")):
                raise ValueError("The proposal changed after the preview")
            if application.action == "update":
                source = await session.scalar(
                    select(Routine).where(
                        Routine.external_id == plan.source_routine_id,
                        Routine.deleted_at.is_(None),
                    )
                )
                if source is None or source.content_hash != application.source_routine_hash:
                    raise ValueError("The source routine changed after the preview")
            application.status = "applying"
            await session.flush()
            if application.action not in {"create", "update"}:
                raise ValueError("Routine application action is invalid")
            action = cast(Literal["create", "update"], application.action)
            return RoutineApplicationCommand(
                application_id=application.id,
                proposal_id=proposal_id,
                action=action,
                source_routine_id=plan.source_routine_id,
                source_routine_hash=application.source_routine_hash,
                plan=plan,
            )

    async def finish_routine_application(
        self,
        application_id: UUID,
        *,
        status: Literal["applied", "failed", "uncertain", "partial"],
        routine_ids: list[str],
        error_type: str | None,
    ) -> None:
        async with self._session_factory.begin() as session:
            application = await session.get(
                RoutineApplication, application_id, with_for_update=True
            )
            if application is None:
                raise ValueError("Routine application was not found")
            application.status = status
            application.result_routine_ids = routine_ids
            application.error_type = error_type
            application.applied_at = datetime.now(UTC)

    async def get_routine_application_reconciliation_context(
        self, proposal_id: UUID
    ) -> RoutineApplicationReconciliationContext | None:
        async with self._session_factory() as session:
            application = await session.scalar(
                select(RoutineApplication).where(RoutineApplication.proposal_id == proposal_id)
            )
            if application is None:
                return None
            if application.status not in {"uncertain", "partial"}:
                raise ValueError("Only uncertain or partial applications can be reconciled")
            if application.applied_at is None:
                raise ValueError("The application has no recorded attempt time")
            proposal = await session.get(CoachProposal, proposal_id)
            if proposal is None:
                return None
            if application.action not in {"create", "update"}:
                raise ValueError("Routine application action is invalid")
            return RoutineApplicationReconciliationContext(
                application_id=application.id,
                proposal_id=proposal_id,
                action=cast(Literal["create", "update"], application.action),
                status=cast(Literal["uncertain", "partial"], application.status),
                applied_at=application.applied_at,
                recorded_routine_ids=application.result_routine_ids,
                plan=_to_public_plan(CoachProposalOutput.model_validate(proposal.proposal_data)),
            )

    async def reconcile_routine_application(
        self,
        application_id: UUID,
        *,
        status: Literal["applied", "partial", "uncertain"],
        routine_ids: list[str],
        error_type: str | None,
    ) -> None:
        async with self._session_factory.begin() as session:
            application = await session.get(
                RoutineApplication, application_id, with_for_update=True
            )
            if application is None:
                raise ValueError("Routine application was not found")
            if application.status not in {"uncertain", "partial"}:
                raise ValueError("Only uncertain or partial applications can be reconciled")
            application.status = status
            application.result_routine_ids = routine_ids
            application.error_type = error_type

    async def acknowledge_workout_review(
        self, review_id: UUID
    ) -> WorkoutReviewAcknowledgement | None:
        async with self._session_factory.begin() as session:
            row = await AutomationRepository(session).complete(
                review_id, completed_at=datetime.now(UTC)
            )
            if row is None:
                return None
            return WorkoutReviewAcknowledgement(
                review_id=row.id,
                workout_external_id=row.workout_external_id,
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
                        superset_group=exercise.superset_group,
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
                            "superset_group": exercise.superset_group,
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


def _stable_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _validate_hevy_compatible_plan(plan: TrainingPlanProposalInput) -> None:
    for workout in plan.workouts:
        for exercise in workout.exercises:
            if exercise.exercise_template_external_id is None:
                raise ValueError("Every exercise needs a Hevy exercise template before application")
            for planned_set in exercise.sets:
                if (
                    planned_set.duration_seconds_min is not None
                    and planned_set.duration_seconds_min != planned_set.duration_seconds_max
                ):
                    raise ValueError("Hevy requires one exact duration value per routine set")
                if (
                    planned_set.distance_meters_min is not None
                    and planned_set.distance_meters_min != planned_set.distance_meters_max
                ):
                    raise ValueError("Hevy requires one exact distance value per routine set")
                if (
                    planned_set.distance_meters_min is not None
                    and planned_set.distance_meters_min
                    != planned_set.distance_meters_min.to_integral_value()
                ):
                    raise ValueError("Hevy requires distance in whole meters")
