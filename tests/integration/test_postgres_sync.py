import os
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
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
from gym_coach.persistence.models import (
    AthleteProfileVersion,
    CoachProposal,
    ExerciseTemplate,
    HevyUser,
    Routine,
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


def test_migration_upgrade_and_downgrade(postgres_database: str) -> None:
    del postgres_database
    config = _alembic_config()
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")


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
                },
                "user_confirmed": True,
            },
        )
        updated_profile = await mcp_client.call_tool(
            "save_confirmed_athlete_profile",
            {
                "profile": {
                    "experience_level": "intermediate",
                    "training_days_per_week": 4,
                    "session_duration_minutes": 60,
                    "equipment": ["full gym"],
                    "limitations": [],
                    "preferences": ["four sessions", "balanced progression"],
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
    routine_route = respx.get("https://hevy.test/v1/routines").mock(
        return_value=httpx.Response(
            200,
            json={
                "page": 1,
                "page_count": 1,
                "routines": [
                    {
                        "id": "routine-1",
                        "title": "Test Routine",
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
            },
        )
    )
    workout = {
        "id": "workout-1",
        "title": "Test Workout",
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
    assert fourth.counts.updated == 1
    assert user_route.call_count == 4
    assert template_route.call_count == 4
    assert routine_route.call_count == 4
    assert workout_route.call_count == 4

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(SyncRun)) == 4
        assert await session.scalar(select(func.count()).select_from(HevyUser)) == 1
        assert await session.scalar(select(func.count()).select_from(ExerciseTemplate)) == 1
        assert await session.scalar(select(func.count()).select_from(Routine)) == 1
        assert await session.scalar(select(func.count()).select_from(Workout)) == 1
        persisted_workout = await session.scalar(select(Workout))
        assert persisted_workout is not None
        assert persisted_workout.deleted_at is None
        assert persisted_workout.deleted_sync_id is None
        assert persisted_workout.title == "Updated Test Workout"

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
    )
    async with Client(create_mcp_server(mcp_tools)) as mcp_client:
        routines = await mcp_client.call_tool("list_training_routines", {})
        routine = await mcp_client.call_tool("get_training_routine", {"routine_id": "routine-1"})
        workouts = await mcp_client.call_tool("get_recent_workouts", {"limit": 1})
        workout_detail = await mcp_client.call_tool("get_workout", {"workout_id": "workout-1"})
        templates = await mcp_client.call_tool(
            "search_exercise_templates", {"query": "press", "limit": 5}
        )

    assert routines.structured_content is not None
    assert routines.structured_content["count"] == 1
    assert routine.structured_content is not None
    assert routine.structured_content["exercises"][0]["sets"][0]["reps"] == 8
    assert workouts.structured_content is not None
    assert workouts.structured_content["count"] == 1
    assert workout_detail.structured_content is not None
    assert workout_detail.structured_content["exercises"][0]["sets"][0]["weight_kg"] == "50.000"
    assert templates.structured_content is not None
    assert templates.structured_content["count"] == 1

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api_client:
        response = await api_client.get(
            "/metrics/summary", params={"days": 7, "target_sessions_per_week": 1}
        )
    assert response.status_code == 200
    assert response.json()["total_volume_kg_reps"] == "400.00"
    await engine.dispose()
