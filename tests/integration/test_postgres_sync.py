import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import httpx
import psycopg
import pytest
import respx
from alembic import command
from alembic.config import Config
from mcp import Client
from psycopg import sql
from pydantic_ai.models.test import TestModel
from sqlalchemy import func, select

from gym_coach.automation.repository import AutomationRepository
from gym_coach.coach.management import CoachManagementService
from gym_coach.coach.schemas import AthleteProfileInput, TrainingGoalInput
from gym_coach.coach.service import CoachService
from gym_coach.config import Settings, get_settings
from gym_coach.db import create_engine, create_session_factory
from gym_coach.integrations.hevy.client import HevyClient
from gym_coach.integrations.hevy.errors import HevyHTTPError
from gym_coach.main import create_app
from gym_coach.mcp.repository import PostgresMCPRepository
from gym_coach.mcp.server import create_mcp_server
from gym_coach.mcp.tools import MCPTools
from gym_coach.metrics.service import MetricsService
from gym_coach.nutrition.service import NutritionService
from gym_coach.persistence.models import (
    AthleteProfileVersion,
    CoachProposal,
    ExerciseTemplate,
    HevyUser,
    Routine,
    RoutineVersion,
    SyncRun,
    TrainingGoal,
    Workout,
)
from gym_coach.sync.hevy import HevySyncService

pytestmark = pytest.mark.postgres


@pytest.fixture
def postgres_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    if os.getenv("GYM_COACH_RUN_POSTGRES_TESTS") != "1":
        pytest.skip("set GYM_COACH_RUN_POSTGRES_TESTS=1 to run PostgreSQL integration tests")
    admin_url = "postgresql://gym_coach:gym_coach@localhost:5432/postgres"
    database_name = f"gym_coach_test_{uuid4().hex}"
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    database_url = f"postgresql+psycopg://gym_coach:gym_coach@localhost:5432/{database_name}"
    monkeypatch.setenv("GYM_COACH_DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        yield database_url
    finally:
        get_settings.cache_clear()
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))


def _alembic_config() -> Config:
    return Config("alembic.ini")


async def test_nutrition_diary_snapshots_retries_recipes_and_corrections(
    postgres_database: str,
) -> None:
    from datetime import date

    from gym_coach.nutrition.schemas import FoodInput, MealInput, Portion, RecipeInput
    from gym_coach.nutrition.service import NutritionService

    command.upgrade(_alembic_config(), "head")
    engine = create_engine(postgres_database)
    service = NutritionService(create_session_factory(engine))
    food = FoodInput.model_validate(
        {
            "name": "Example yoghurt",
            "brand": "Anonymous",
            "barcode": "1234567890123",
            "state": "as_sold",
            "basis_unit": "g",
            "serving_size": "125",
            "serving_unit": "g",
            "source": "label",
            "source_reference": "User label confirmed",
            "nutrients_per_100": {
                "energy_kcal": "60",
                "protein_g": "4",
                "carbohydrate_g": "5",
                "fat_g": "3",
            },
        }
    )
    try:
        food_id = uuid4()
        with pytest.raises(ValueError, match="confirmation"):
            await service.save_food(food_id, food, False)
        assert await service.search("yoghurt") == []
        saved = await service.save_food(food_id, food, True)
        assert await service.save_food(food_id, food, True) == saved
        barcode_results = await service.search("1234567890123")
        assert [item.id for item in barcode_results] == [food_id]
        serving_preview = await service.preview(
            MealInput(
                consumed_at=datetime.fromisoformat("2026-09-14T08:00:00+02:00"),
                meal="breakfast",
                items=[Portion(item_id=food_id, quantity=Decimal("1"), unit="serving")],
            )
        )
        assert serving_preview.totals.energy_kcal == Decimal("75")
        with pytest.raises(ValueError, match="different data"):
            await service.save_food(food_id, food.model_copy(update={"name": "Changed"}), True)
        portion = Portion(item_id=food_id, quantity=Decimal("200"), unit="g")
        recipe = RecipeInput(name="Usual breakfast", ingredients=[portion], servings=Decimal("2"))
        recipe_id = uuid4()
        await service.save_recipe(recipe_id, recipe, True)
        meal = MealInput(
            consumed_at=datetime.fromisoformat("2026-09-14T00:30:00+02:00"),
            meal="breakfast",
            items=[Portion(item_id=recipe_id, quantity=Decimal("1"), unit="serving")],
        )
        preview = await service.preview(meal)
        assert preview.totals.energy_kcal == Decimal("60")
        assert preview.totals.fiber_g is None
        assert not preview.estimated
        meal_id = uuid4()
        logged = await service.log_meal(meal_id, meal, True)
        assert await service.log_meal(meal_id, meal, True) == logged
        assert (await service.daily(date(2026, 9, 13), "Europe/Madrid")).entries == []
        daily = await service.daily(date(2026, 9, 14), "Europe/Madrid")
        assert len(daily.entries) == 1
        assert daily.totals.energy_kcal == Decimal("60")
        assert len((await service.daily(date(2026, 9, 13), "UTC")).entries) == 1
        assert daily.coverage == "logged_meals_only"
        await service.save_food(uuid4(), food.model_copy(update={"name": "New version"}), True)
        assert (await service.daily(date(2026, 9, 14), "Europe/Madrid")).totals == daily.totals
        await service.void(meal_id, "Wrong portion", True)
        await service.void(meal_id, "Wrong portion", True)
        corrected = await service.daily(date(2026, 9, 14), "Europe/Madrid")
        assert corrected.entries[0].voided
        assert corrected.totals.energy_kcal == 0
        invalid = meal.model_copy(
            update={"items": [Portion(item_id=food_id, quantity=Decimal("2"), unit="ml")]}
        )
        with pytest.raises(ValueError, match="unit"):
            await service.preview(invalid)
        invalid = meal.model_copy(
            update={"items": [Portion(item_id=uuid4(), quantity=Decimal("2"), unit="g")]}
        )
        with pytest.raises(ValueError, match="Unknown"):
            await service.preview(invalid)
        estimated_id = uuid4()
        await service.save_food(estimated_id, food.model_copy(update={"source": "estimate"}), True)
        estimate = meal.model_copy(
            update={"items": [Portion(item_id=estimated_id, quantity=Decimal("100"), unit="g")]}
        )
        assert (await service.preview(estimate)).estimated
        with pytest.raises(ValueError, match="timezone"):
            await service.daily(date(2026, 9, 14), "not-a-zone")

        settings = Settings(_env_file=None, GYM_COACH_DATABASE_URL=postgres_database)
        tools = MCPTools(
            settings,
            PostgresMCPRepository(create_session_factory(engine)),
            MetricsService(create_session_factory(engine)),
            lambda: HevyClient("unused"),
            nutrition=service,
        )
        async with Client(create_mcp_server(tools)) as client:
            result = await client.call_tool("get_daily_nutrition", {"day": "2026-09-14"})
            assert not result.is_error
            rejected = await client.call_tool(
                "save_nutrition_food",
                {
                    "request_id": str(uuid4()),
                    "food": food.model_dump(mode="json"),
                    "user_confirmed": False,
                },
            )
            assert rejected.is_error
    finally:
        await engine.dispose()


def test_migration_upgrade_and_downgrade(postgres_database: str) -> None:
    del postgres_database
    config = _alembic_config()
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")


async def test_automatic_workout_review_queue_is_idempotent_and_recoverable(
    postgres_database: str,
) -> None:
    command.upgrade(_alembic_config(), "head")
    engine = create_engine(postgres_database)
    factory = create_session_factory(engine)
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)

    async with factory.begin() as session:
        repository = AutomationRepository(session)
        assert await repository.initialize_cursor("hevy_workouts", now)
        assert not await repository.initialize_cursor("hevy_workouts", now)
        await repository.enqueue_workout("anonymous-workout")
        await repository.enqueue_workout("anonymous-workout")

    async with factory.begin() as session:
        claimed = await AutomationRepository(session).claim_next(
            now=now, stale_after=timedelta(minutes=30)
        )
        assert claimed is not None
        review_id = claimed.id
        assert claimed.attempt_count == 1

    async with factory.begin() as session:
        assert (
            await AutomationRepository(session).claim_next(
                now=now + timedelta(minutes=1), stale_after=timedelta(minutes=30)
            )
            is None
        )

    retry_at = now + timedelta(minutes=31)
    async with factory.begin() as session:
        retried = await AutomationRepository(session).claim_next(
            now=retry_at, stale_after=timedelta(minutes=30)
        )
        assert retried is not None
        assert retried.id == review_id
        assert retried.attempt_count == 2
        completed = await AutomationRepository(session).complete(review_id, completed_at=retry_at)
        assert completed is not None
        assert completed.status == "completed"

    async with factory.begin() as session:
        assert (
            await AutomationRepository(session).complete(review_id, completed_at=retry_at) is None
        )

    await engine.dispose()


@respx.mock
async def test_failed_download_is_traced_without_domain_writes(postgres_database: str) -> None:
    command.upgrade(_alembic_config(), "head")
    respx.get("https://hevy.test/v1/user/info").mock(return_value=httpx.Response(401))
    engine = create_engine(postgres_database)
    factory = create_session_factory(engine)
    async with httpx.AsyncClient(base_url="https://hevy.test") as http_client:
        client = HevyClient("test-placeholder", http_client=http_client, retry_attempts=1)
        with pytest.raises(HevyHTTPError):
            await HevySyncService(client, factory).sync()

    async with factory() as session:
        run = await session.scalar(select(SyncRun))
        assert run is not None
        assert run.status == "failed"
        assert run.error_type == "HevyHTTPError"
        assert await session.scalar(select(func.count()).select_from(HevyUser)) == 0
    await engine.dispose()


async def test_coach_persists_profile_goal_and_approved_draft_without_hevy_write(
    postgres_database: str,
) -> None:
    command.upgrade(_alembic_config(), "head")
    engine = create_engine(postgres_database)
    factory = create_session_factory(engine)
    management = CoachManagementService(factory)
    profile = await management.set_profile(
        AthleteProfileInput(
            experience_level="intermediate",
            training_days_per_week=3,
            session_duration_minutes=60,
            equipment=["barbell"],
        )
    )
    goal = await management.add_goal(
        TrainingGoalInput(goal_type="strength", description="Improve compound lifts", priority=1)
    )
    model = TestModel(
        custom_output_args={
            "answer": "Propongo un borrador de tres días.",
            "evidence_ids": ["goal.1", "profile.training_days"],
            "findings": [
                {
                    "statement": "El objetivo activo es fuerza.",
                    "evidence_ids": ["goal.1"],
                }
            ],
            "proposal": {
                "kind": "new_routine",
                "title": "Strength 3 days",
                "summary": "Three full-body days",
                "rationale": "Matches the active goal and availability",
                "evidence_ids": ["goal.1", "profile.training_days"],
                "source_routine_id": None,
                "workouts": [
                    {
                        "title": "Day A",
                        "exercises": [
                            {
                                "exercise_template_id": None,
                                "title": "Squat",
                                "rest_seconds": 180,
                                "sets": [
                                    {
                                        "set_type": "normal",
                                        "reps_min": 5,
                                        "reps_max": 5,
                                        "target_rpe": 8,
                                        "load_guidance": "Choose from recent performance",
                                    }
                                ],
                                "notes": None,
                            }
                        ],
                    }
                ],
            },
        }
    )
    result = await CoachService(factory, model=model, model_name="test").ask(
        "Create a strength routine", as_of=datetime(2026, 8, 6, tzinfo=UTC)
    )
    assert result.stored_proposal is not None
    approved = await management.decide(result.stored_proposal.id, "approved")

    assert profile.training_days_per_week == 3
    assert goal.version == 1
    assert approved.status == "approved"
    assert await management.list_proposals() == [approved]
    assert profile.version == 1
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(AthleteProfileVersion)) == 1
        stored_goal = await session.scalar(select(TrainingGoal))
        assert stored_goal is not None
        assert stored_goal.user_confirmed is True
        assert stored_goal.source == "cli"
    await engine.dispose()


async def test_mcp_confirmed_onboarding_metrics_and_local_plan_cycle(
    postgres_database: str,
) -> None:
    command.upgrade(_alembic_config(), "head")
    engine = create_engine(postgres_database)
    factory = create_session_factory(engine)
    settings = Settings(
        _env_file=None,
        GYM_COACH_DATABASE_URL=postgres_database,
        HEVY_API_KEY=None,
    )
    tools = MCPTools(
        settings,
        PostgresMCPRepository(factory),
        MetricsService(factory),
        lambda: HevyClient("not-used", retry_attempts=1),
    )

    async with Client(create_mcp_server(tools)) as mcp_client:
        initial = await mcp_client.call_tool("get_onboarding_status", {})
        rejected_profile = await mcp_client.call_tool(
            "save_confirmed_athlete_profile",
            {
                "profile": {
                    "experience_level": "intermediate",
                    "birth_year": 1990,
                    "sex_for_energy_equation": "male",
                    "height_cm": "180",
                    "training_days_per_week": 4,
                },
                "user_confirmed": False,
            },
        )
        profile = await mcp_client.call_tool(
            "save_confirmed_athlete_profile",
            {
                "profile": {
                    "experience_level": "intermediate",
                    "training_days_per_week": 4,
                    "session_duration_minutes": 60,
                    "equipment": ["full gym"],
                    "limitations": [],
                    "preferences": ["four sessions"],
                    "limitations_reviewed": True,
                    "preferences_reviewed": True,
                    "lifestyle_reviewed": True,
                    "nutrition_reviewed": True,
                    "health_reviewed": True,
                    "occupation_activity": "sedentary",
                    "sleep_hours": 7.5,
                    "dietary_pattern": "omnivore",
                },
                "user_confirmed": True,
            },
        )
        updated_profile = await mcp_client.call_tool(
            "save_confirmed_athlete_profile",
            {
                "profile": {
                    "experience_level": "intermediate",
                    "birth_year": 1990,
                    "sex_for_energy_equation": "male",
                    "height_cm": "180",
                    "training_days_per_week": 4,
                    "session_duration_minutes": 60,
                    "equipment": ["full gym"],
                    "limitations": [],
                    "preferences": ["four sessions", "balanced progression"],
                    "limitations_reviewed": True,
                    "preferences_reviewed": True,
                    "lifestyle_reviewed": True,
                    "nutrition_reviewed": True,
                    "health_reviewed": True,
                    "occupation_activity": "sedentary",
                    "sleep_hours": 7.5,
                    "dietary_pattern": "omnivore",
                },
                "user_confirmed": True,
            },
        )
        first_goal = await mcp_client.call_tool(
            "add_confirmed_training_goal",
            {
                "goal": {
                    "goal_type": "hypertrophy",
                    "description": "Build muscle sustainably",
                    "priority": 1,
                },
                "user_confirmed": True,
            },
        )
        revised_goal = await mcp_client.call_tool(
            "revise_confirmed_training_goal",
            {
                "goal_version": 1,
                "goal": {
                    "goal_type": "hypertrophy",
                    "description": "Build muscle with four weekly sessions",
                    "priority": 1,
                },
                "user_confirmed": True,
            },
        )
        measurement = await mcp_client.call_tool(
            "save_confirmed_athlete_measurement",
            {
                "measurement": {"measured_on": "2026-08-06", "weight_kg": "80"},
                "user_confirmed": True,
            },
        )
        check_in = await mcp_client.call_tool(
            "save_confirmed_athlete_check_in",
            {
                "check_in": {
                    "checked_on": "2026-08-06",
                    "sleep_quality": 4,
                    "energy_level": 4,
                    "training_adherence": 5,
                },
                "user_confirmed": True,
            },
        )
        coaching = await mcp_client.call_tool("get_coaching_assessment", {})
        metrics = await mcp_client.call_tool("get_training_metrics", {"window_days": 28})
        assert metrics.structured_content is not None
        evidence_id = metrics.structured_content["evidence_id"]
        draft = await mcp_client.call_tool(
            "create_training_plan_proposal",
            {
                "plan": {
                    "kind": "new_routine",
                    "title": "Four-day draft",
                    "summary": "Local draft for review",
                    "rationale": "Matches the confirmed goal and availability",
                    "evidence_ids": [evidence_id],
                    "changes": [
                        {
                            "description": "Match the confirmed weekly availability",
                            "evidence_ids": [evidence_id],
                        }
                    ],
                    "workouts": [
                        {
                            "title": "Upper A",
                            "exercises": [
                                {
                                    "title": "Example press",
                                    "rest_seconds": 180,
                                    "sets": [{"reps_min": 6, "reps_max": 8}],
                                }
                            ],
                        }
                    ],
                },
                "user_requested": True,
            },
        )
        assert draft.structured_content is not None
        proposal_id = draft.structured_content["proposal_id"]
        comparison = await mcp_client.call_tool(
            "compare_training_plan_proposal", {"proposal_id": proposal_id}
        )
        decision = await mcp_client.call_tool(
            "decide_training_plan_proposal",
            {
                "proposal_id": proposal_id,
                "decision": "approved",
                "user_confirmed": True,
            },
        )

    assert initial.structured_content is not None
    assert initial.structured_content["ready_for_training_analysis"] is False
    assert rejected_profile.is_error is True
    assert profile.structured_content is not None
    assert profile.structured_content["profile_version"] == 1
    assert updated_profile.structured_content is not None
    assert updated_profile.structured_content["profile_version"] == 2
    assert first_goal.structured_content is not None
    assert first_goal.structured_content["goal_version"] == 1
    assert revised_goal.structured_content is not None
    assert revised_goal.structured_content["goal_version"] == 2
    assert measurement.structured_content is not None
    assert check_in.structured_content is not None
    assert coaching.structured_content is not None
    assert coaching.structured_content["protein_range_g_per_day"] == [112, 160]
    assert coaching.structured_content["history"]["history_level"] == "insufficient"
    assert comparison.structured_content is not None
    assert comparison.structured_content["changes_are_applied"] is False
    assert decision.structured_content is not None
    assert decision.structured_content["status"] == "approved"
    assert decision.structured_content["applied_to_hevy"] is False

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(AthleteProfileVersion)) == 2
        goals = (await session.scalars(select(TrainingGoal).order_by(TrainingGoal.version))).all()
        assert [item.status for item in goals] == ["archived", "active"]
        assert all(item.user_confirmed for item in goals)
        assert all(item.source == "hermes_mcp" for item in goals)
        proposal = await session.scalar(select(CoachProposal))
        assert proposal is not None
        assert proposal.request_source == "hermes_mcp"
        assert proposal.user_requested is True
        assert proposal.decision_source == "hermes_mcp"
        assert proposal.decision_user_confirmed is True
    await engine.dispose()


@respx.mock
async def test_full_sync_is_idempotent_and_traces_deletions(postgres_database: str) -> None:
    command.upgrade(_alembic_config(), "head")
    user_route = respx.get("https://hevy.test/v1/user/info").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": "user-1", "name": "Test Athlete", "url": None}},
        )
    )
    template_route = respx.get("https://hevy.test/v1/exercise_templates").mock(
        return_value=httpx.Response(
            200,
            json={
                "page": 1,
                "page_count": 1,
                "exercise_templates": [
                    {
                        "id": "template-1",
                        "title": "Test Press",
                        "type": "weight_reps",
                        "primary_muscle_group": "chest",
                        "secondary_muscle_groups": ["triceps"],
                        "equipment": "barbell",
                        "is_custom": False,
                    }
                ],
            },
        )
    )
    original_routine_page = {
        "page": 1,
        "page_count": 1,
        "routines": [
            {
                "id": "routine-1",
                "title": "Test Routine",
                "updated_at": "2026-08-01T10:00:00Z",
                "exercises": [
                    {
                        "index": 0,
                        "title": "Test Press",
                        "exercise_template_id": "template-1",
                        "sets": [{"index": 0, "type": "normal", "reps": 8}],
                    }
                ],
            }
        ],
    }
    changed_routine_page = {
        "page": 1,
        "page_count": 1,
        "routines": [
            {
                "id": "routine-1",
                "title": "Test Routine",
                "updated_at": "2026-08-10T10:00:00Z",
                "exercises": [
                    {
                        "index": 0,
                        "title": "Test Press",
                        "exercise_template_id": "template-1",
                        "sets": [{"index": 0, "type": "normal", "reps": 10}],
                    }
                ],
            }
        ],
    }
    routine_route = respx.get("https://hevy.test/v1/routines")
    routine_route.side_effect = [
        httpx.Response(200, json=original_routine_page),
        httpx.Response(200, json=original_routine_page),
        httpx.Response(200, json=original_routine_page),
        httpx.Response(200, json=changed_routine_page),
    ]
    workout = {
        "id": "workout-1",
        "title": "Test Workout",
        "routine_id": "routine-1",
        "start_time": "2026-08-05T10:00:00Z",
        "end_time": "2026-08-05T11:00:00Z",
        "exercises": [
            {
                "index": 0,
                "title": "Test Press",
                "exercise_template_id": "template-1",
                "sets": [{"index": 0, "type": "normal", "weight_kg": 50, "reps": 8}],
            }
        ],
    }
    workout_route = respx.get("https://hevy.test/v1/workouts")
    restored_workout = {**workout, "title": "Updated Test Workout"}
    workout_route.side_effect = [
        httpx.Response(200, json={"page": 1, "page_count": 1, "workouts": [workout]}),
        httpx.Response(200, json={"page": 1, "page_count": 1, "workouts": [workout]}),
        httpx.Response(200, json={"page": 1, "page_count": 1, "workouts": []}),
        httpx.Response(200, json={"page": 1, "page_count": 1, "workouts": [restored_workout]}),
    ]
    engine = create_engine(postgres_database)
    factory = create_session_factory(engine)
    async with httpx.AsyncClient(base_url="https://hevy.test") as http_client:
        client = HevyClient(
            "test-placeholder",
            http_client=http_client,
            retry_attempts=1,
        )
        service = HevySyncService(client, factory)
        first = await service.sync()
        second = await service.sync()
        third = await service.sync()
        async with factory() as session:
            deleted_workout = await session.scalar(select(Workout))
            assert deleted_workout is not None
            assert str(deleted_workout.deleted_sync_id) == third.run_id
        fourth = await service.sync()

    assert first.counts.inserted == 4
    assert second.counts.unchanged == 4
    assert second.counts.inserted == 0
    assert second.counts.updated == 0
    assert second.counts.deleted == 0
    assert third.counts.deleted == 1
    assert fourth.counts.updated == 2
    assert user_route.call_count == 4
    assert template_route.call_count == 4
    assert routine_route.call_count == 4
    assert workout_route.call_count == 4

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(SyncRun)) == 4
        assert await session.scalar(select(func.count()).select_from(HevyUser)) == 1
        assert await session.scalar(select(func.count()).select_from(ExerciseTemplate)) == 1
        assert await session.scalar(select(func.count()).select_from(Routine)) == 1
        assert await session.scalar(select(func.count()).select_from(RoutineVersion)) == 2
        assert await session.scalar(select(func.count()).select_from(Workout)) == 1
        persisted_workout = await session.scalar(select(Workout))
        assert persisted_workout is not None
        assert persisted_workout.deleted_at is None
        assert persisted_workout.deleted_sync_id is None
        assert persisted_workout.title == "Updated Test Workout"
        assert persisted_workout.routine_version_id is not None

    metrics = MetricsService(factory)
    summary = await metrics.summary(
        as_of=datetime(2026, 8, 6, tzinfo=UTC),
        window_days=7,
        target_sessions_per_week=Decimal("1"),
    )
    report = await metrics.exercise_report(
        "template-1", as_of=datetime(2026, 8, 6, tzinfo=UTC), window_days=7
    )
    reports = await metrics.exercise_reports(
        ["template-1", "template-1"],
        as_of=datetime(2026, 8, 6, tzinfo=UTC),
        window_days=7,
    )
    assert summary.workouts == 1
    assert summary.total_reps == 8
    assert summary.total_volume_kg_reps == Decimal("400.00")
    assert report.progress.latest_e1rm_kg == Decimal("63.33")
    assert len(reports) == 1
    assert reports[0].progress.latest_e1rm_kg == Decimal("63.33")

    mcp_tools = MCPTools(
        Settings(_env_file=None, GYM_COACH_DATABASE_URL=postgres_database),
        PostgresMCPRepository(factory),
        MetricsService(factory),
        lambda: client,
        nutrition=NutritionService(factory),
    )
    async with Client(create_mcp_server(mcp_tools)) as mcp_client:
        routines = await mcp_client.call_tool("list_training_routines", {})
        routine = await mcp_client.call_tool("get_training_routine", {"routine_id": "routine-1"})
        workouts = await mcp_client.call_tool("get_recent_workouts", {"limit": 1})
        workout_detail = await mcp_client.call_tool("get_workout", {"workout_id": "workout-1"})
        prescription = await mcp_client.call_tool(
            "compare_workout_to_current_routine", {"workout_id": "workout-1"}
        )
        coaching_review = await mcp_client.call_tool(
            "get_workout_coaching_review",
            {"workout_id": "workout-1", "timezone": "Europe/Madrid"},
        )
        templates = await mcp_client.call_tool(
            "search_exercise_templates", {"query": "press", "limit": 5}
        )
        await mcp_client.call_tool(
            "save_confirmed_athlete_profile",
            {
                "profile": {
                    "experience_level": "intermediate",
                    "training_days_per_week": 3,
                    "session_duration_minutes": 60,
                    "equipment": ["full gym"],
                    "limitations": [],
                    "preferences": [],
                    "limitations_reviewed": True,
                    "preferences_reviewed": True,
                    "lifestyle_reviewed": True,
                    "nutrition_reviewed": True,
                    "health_reviewed": True,
                },
                "user_confirmed": True,
            },
        )
        plan_metrics = await mcp_client.call_tool("get_training_metrics", {"window_days": 28})
        assert plan_metrics.structured_content is not None
        metric_evidence = plan_metrics.structured_content["evidence_id"]
        plan_draft = await mcp_client.call_tool(
            "create_training_plan_proposal",
            {
                "plan": {
                    "kind": "routine_update",
                    "title": "Updated test routine",
                    "summary": "A deterministic comparison fixture",
                    "rationale": "Tests retained exercises and set deltas",
                    "evidence_ids": [metric_evidence, "routine:routine-1"],
                    "source_routine_id": "routine-1",
                    "changes": [
                        {
                            "description": "Add one set to the retained press",
                            "evidence_ids": [metric_evidence, "routine:routine-1"],
                        }
                    ],
                    "workouts": [
                        {
                            "title": "Updated day",
                            "location": "gym",
                            "estimated_duration_minutes": 45,
                            "exercises": [
                                {
                                    "exercise_template_external_id": "template-1",
                                    "title": "Test Press",
                                    "rest_seconds": 120,
                                    "sets": [
                                        {"reps_min": 8, "reps_max": 10},
                                        {"reps_min": 8, "reps_max": 10},
                                    ],
                                }
                            ],
                        }
                    ],
                },
                "user_requested": True,
            },
        )
        assert plan_draft.structured_content is not None
        detailed_comparison = await mcp_client.call_tool(
            "compare_training_plan_proposal",
            {"proposal_id": plan_draft.structured_content["proposal_id"]},
        )
        approved_plan = await mcp_client.call_tool(
            "decide_training_plan_proposal",
            {
                "proposal_id": plan_draft.structured_content["proposal_id"],
                "decision": "approved",
                "user_confirmed": True,
            },
        )
        assert approved_plan.structured_content is not None
        application_preview = await mcp_client.call_tool(
            "preview_training_plan_application",
            {"proposal_id": plan_draft.structured_content["proposal_id"]},
        )

    assert routines.structured_content is not None
    assert routines.structured_content["count"] == 1
    assert routine.structured_content is not None
    assert routine.structured_content["exercises"][0]["sets"][0]["reps"] == 10
    assert workouts.structured_content is not None
    assert workouts.structured_content["count"] == 1
    assert workout_detail.structured_content is not None
    assert workout_detail.structured_content["exercises"][0]["sets"][0]["weight_kg"] == "50.000"
    assert prescription.structured_content is not None
    assert prescription.structured_content["prescription_source"] == "historical_snapshot"
    assert prescription.structured_content["met_sets"] == 1
    assert coaching_review.structured_content is not None
    assert coaching_review.structured_content["comparison"]["prescription_source"] == (
        "historical_snapshot"
    )
    assert coaching_review.structured_content["exercise_progress"][0]["period_end"] == (
        "2026-08-05T11:00:00Z"
    )
    assert templates.structured_content is not None
    assert templates.structured_content["count"] == 1
    assert detailed_comparison.structured_content is not None
    assert application_preview.structured_content is not None
    assert application_preview.structured_content["action"] == "update"
    assert application_preview.structured_content["source_routine_id"] == "routine-1"
    assert application_preview.structured_content["confirmation_token"]
    assert detailed_comparison.structured_content["exercise_changes"] == [
        {
            "exercise_template_external_id": "template-1",
            "title": "Test Press",
            "change": "retained",
            "current_frequency": 1,
            "proposed_frequency": 1,
            "current_sets": 1,
            "proposed_sets": 2,
            "set_delta": 1,
        }
    ]
    assert detailed_comparison.structured_content["muscle_group_changes"] == [
        {
            "muscle_group": "chest",
            "current_sets": 1,
            "proposed_sets": 2,
            "set_delta": 1,
            "current_indirect_sets": "0",
            "proposed_indirect_sets": "0",
            "current_total_stimulus_sets": "1",
            "proposed_total_stimulus_sets": "2",
            "total_stimulus_delta": "1",
        },
        {
            "muscle_group": "triceps",
            "current_sets": 0,
            "proposed_sets": 0,
            "set_delta": 0,
            "current_indirect_sets": "0.5",
            "proposed_indirect_sets": "1.0",
            "current_total_stimulus_sets": "0.5",
            "proposed_total_stimulus_sets": "1.0",
            "total_stimulus_delta": "0.5",
        },
    ]

    transport = httpx.ASGITransport(app=create_app())
    with patch("gym_coach.api.metrics.datetime") as api_clock:
        api_clock.now.return_value = datetime(2026, 8, 6, tzinfo=UTC)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as api_client:
            response = await api_client.get(
                "/metrics/summary", params={"days": 7, "target_sessions_per_week": 1}
            )
    assert response.status_code == 200
    assert response.json()["total_volume_kg_reps"] == "400.00"
    await engine.dispose()


async def test_targets_coverage_trends_and_health_import(postgres_database: str) -> None:
    from datetime import date, timedelta

    from gym_coach.integrations.health_connect.service import HealthBatch, HealthConnectService
    from gym_coach.mcp.schemas import (
        AthleteCheckInInput,
        AthleteMeasurementInput,
        AthleteProfileUpdate,
    )
    from gym_coach.tracking.activity import ActivityDay
    from gym_coach.tracking.body import BodyMeasurementObservation
    from gym_coach.tracking.schemas import DayClosure, TargetParameters
    from gym_coach.tracking.service import TrackingService

    command.upgrade(_alembic_config(), "head")
    engine = create_engine(postgres_database)
    factory = create_session_factory(engine)
    repository = PostgresMCPRepository(factory)
    tracking = TrackingService(factory)
    today = date.today()
    try:
        await repository.save_profile(
            AthleteProfileUpdate(
                training_days_per_week=3,
                birth_year=today.year - 30,
                height_cm=Decimal(180),
                sex_for_energy_equation="male",
                health_reviewed=True,
                nutrition_reviewed=True,
                lifestyle_reviewed=True,
                limitations_reviewed=True,
                preferences_reviewed=True,
            )
        )
        await repository.save_measurement(
            AthleteMeasurementInput(measured_on=today - timedelta(days=1), weight_kg=Decimal(80))
        )
        await repository.save_measurement(
            AthleteMeasurementInput(measured_on=today, waist_cm=Decimal(90))
        )
        assert (await repository.coaching_assessment()).latest_weight_kg is not None
        await repository.save_check_in(AthleteCheckInInput(checked_on=today, soreness_level=4))
        params = TargetParameters(
            effective_from=today,
            activity_factor=Decimal("1.5"),
            energy_adjustment_percent=Decimal(-10),
            protein_g_per_kg=Decimal("1.6"),
            fat_energy_percent=Decimal(30),
            rationale="Confirmed sustainable target and moderate activity",
        )
        from gym_coach.mcp.schemas import TrainingGoalUpdate

        await repository.add_goal(
            TrainingGoalUpdate(goal_type="fat_loss", description="Gradual fat loss")
        )
        preview = await tracking.preview_target(params)
        with pytest.raises(ValueError, match="confirmation"):
            await tracking.save_target(uuid4(), preview, False)
        version_id = uuid4()
        saved = await tracking.save_target(version_id, preview, True)
        assert await tracking.save_target(version_id, preview, True) == saved
        with pytest.raises(ValueError, match="modified"):
            await tracking.save_target(
                uuid4(), preview.model_copy(update={"resting_energy_kcal": 1}), True
            )
        day = await tracking.day_review(today, "UTC")
        assert day.target is not None and not day.complete and day.difference is None
        closure = DayClosure(
            day=today, timezone="UTC", complete=True, diary_fingerprint=day.diary_fingerprint
        )
        closure_id = uuid4()
        await tracking.close_day(closure_id, closure, True)
        assert (await tracking.day_review(today, "UTC")).complete
        review = await tracking.weekly_review(today, "UTC")
        assert review.complete_days == 1
        assert len(review.check_ins) == 1
        assert len(review.measurements) == 2
        assert any("discomfort" in a for a in review.review_actions)
        assert review.activity.mean_steps is None
        from gym_coach.nutrition.schemas import FoodInput, MealInput, Nutrients, Portion

        food_id = uuid4()
        await tracking.nutrition.save_food(
            food_id,
            FoodInput(
                name="Test food",
                state="as_sold",
                basis_unit="g",
                source="label",
                source_reference="Confirmed test label",
                nutrients_per_100=Nutrients(
                    energy_kcal=100, protein_g=10, fat_g=4, carbohydrate_g=6
                ),
            ),
            True,
        )
        await tracking.nutrition.log_meal(
            uuid4(),
            MealInput(
                consumed_at=datetime.now(UTC),
                meal="lunch",
                items=[Portion(item_id=food_id, quantity=100, unit="g")],
            ),
            True,
        )
        changed = await tracking.day_review(today, "UTC")
        assert not changed.complete and changed.difference is None
        assert await tracking.close_day(closure_id, closure, True) == closure
        assert not (await tracking.day_review(today, "UTC")).complete
        with pytest.raises(ValueError, match="confirmation"):
            await tracking.close_day(closure_id, closure, False)
        with pytest.raises(ValueError, match="changed"):
            await tracking.close_day(uuid4(), closure, True)
        importer = HealthConnectService(factory)
        observed = datetime.now(UTC)
        batch = HealthBatch(
            request_id=uuid4(),
            consent_confirmed=True,
            days=[
                ActivityDay(
                    day=today - timedelta(days=1),
                    timezone="UTC",
                    steps=5000,
                    sleep_session_minutes=Decimal(420),
                    sleep_asleep_minutes=Decimal(390),
                    sleep_deep_minutes=Decimal(75),
                    sleep_rem_minutes=Decimal(90),
                    exercise_session_count=1,
                    exercise_minutes=Decimal(45),
                    exercise_minutes_by_type={"walking": Decimal(45)},
                    distance_meters=Decimal(4000),
                    total_energy_kcal=Decimal(650),
                    heart_rate_sample_count=100,
                    mean_heart_rate_bpm=Decimal(72),
                    min_heart_rate_bpm=50,
                    max_heart_rate_bpm=130,
                    resting_heart_rate_bpm=Decimal(55),
                    hrv_rmssd_ms=Decimal("42.5"),
                    oxygen_saturation_sample_count=20,
                    mean_oxygen_saturation_percent=Decimal(97),
                    min_oxygen_saturation_percent=Decimal(94),
                    vo2_max_ml_min_kg=Decimal("41.8"),
                    observed_at=observed,
                )
            ],
            body_measurements=[
                BodyMeasurementObservation(
                    external_id=uuid4(),
                    measured_at=observed - timedelta(hours=1),
                    measured_on=(observed - timedelta(hours=1)).date(),
                    timezone="UTC",
                    weight_kg=Decimal("79.50"),
                    body_fat_percent=Decimal("18.25"),
                    body_fat_method="consumer_bia",
                    lean_body_mass_kg=Decimal("65.20"),
                    body_water_mass_kg=Decimal("44.80"),
                    bone_mass_kg=Decimal("3.20"),
                    basal_metabolic_rate_kcal=Decimal("1652.01"),
                    observed_at=observed,
                )
            ],
        )
        imported = await importer.ingest(batch)
        assert imported.accepted_body_measurements == 1
        await importer.ingest(batch)
        same_observation = HealthBatch(
            request_id=uuid4(),
            consent_confirmed=True,
            days=[batch.days[0].model_copy(update={"steps": 5001})],
        )
        await importer.ingest(same_observation)
        older = HealthBatch(
            request_id=uuid4(),
            consent_confirmed=True,
            days=[
                batch.days[0].model_copy(
                    update={"steps": 1000, "observed_at": observed - timedelta(minutes=1)}
                )
            ],
        )
        await importer.ingest(older)
        review = await tracking.weekly_review(today, "UTC")
        assert review.activity.mean_steps == 5001
        assert review.activity.mean_sleep_session_minutes == 420
        assert review.activity.mean_sleep_asleep_minutes == 390
        assert review.activity.mean_exercise_minutes == 45
        assert review.activity.total_distance_meters == 4000
        assert review.activity.mean_resting_heart_rate_bpm == 55
        assert review.activity.mean_hrv_rmssd_ms == Decimal("42.50")
        assert review.activity.mean_oxygen_saturation_percent == 97
        assert review.activity.latest_vo2_max_ml_min_kg == Decimal("41.8")
        assert len(review.wearable_measurements) == 1
        assert review.wearable_measurements[0].body_fat_method == "consumer_bia"
        assert review.wearable_measurements[0].lean_body_mass_kg == Decimal("65.20")
        with pytest.raises(ValueError, match="different data"):
            await importer.ingest(batch.model_copy(update={"days": older.days}))
        # A newer empty source snapshot represents deletion/unknown, never a zero measurement.
        cleared = HealthBatch(
            request_id=uuid4(),
            consent_confirmed=True,
            days=[
                ActivityDay(
                    day=today - timedelta(days=1),
                    timezone="UTC",
                    observed_at=observed + timedelta(seconds=1),
                )
            ],
        )
        await importer.ingest(cleared)
        assert (await tracking.weekly_review(today, "UTC")).activity.mean_steps is None
    finally:
        await engine.dispose()
