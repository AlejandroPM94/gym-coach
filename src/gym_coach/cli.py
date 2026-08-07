import argparse
import asyncio
import json
import sys
from collections.abc import Callable, Coroutine
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from gym_coach.automation.service import WorkoutReviewAutomationService
from gym_coach.coach.errors import CoachError
from gym_coach.coach.management import CoachManagementService
from gym_coach.coach.schemas import AthleteProfileInput, TrainingGoalInput
from gym_coach.config import Settings, get_settings
from gym_coach.db import create_engine, create_session_factory
from gym_coach.integrations.hevy.client import HevyClient
from gym_coach.integrations.hevy.errors import HevyConfigurationError, HevyError
from gym_coach.integrations.hevy.raw_store import RawResponseStore
from gym_coach.mcp.server import run_stdio_server
from gym_coach.metrics.service import MetricsError, MetricsService
from gym_coach.metrics.types import StagnationRule
from gym_coach.sync.hevy import HevySyncError, HevySyncService


def _client(settings: Settings) -> HevyClient:
    if settings.hevy_api_key is None or not settings.hevy_api_key.get_secret_value():
        raise HevyConfigurationError("HEVY_API_KEY is not configured; add it to your local .env")
    return HevyClient(
        settings.hevy_api_key,
        base_url=settings.hevy_base_url,
        timeout_seconds=settings.hevy_timeout_seconds,
        retry_attempts=settings.hevy_retry_attempts,
        retry_backoff_seconds=settings.hevy_retry_backoff_seconds,
        raw_store=RawResponseStore(settings.raw_data_dir),
    )


async def _check(settings: Settings, _: argparse.Namespace) -> str:
    async with _client(settings) as client:
        await client.get_user()
    return "Connection to Hevy succeeded."


async def _user(settings: Settings, _: argparse.Namespace) -> str:
    async with _client(settings) as client:
        await client.get_user()
    return "Downloaded Hevy user information."


async def _routines(settings: Settings, _: argparse.Namespace) -> str:
    async with _client(settings) as client:
        routines = await client.get_all_routines()
    return f"Downloaded {len(routines)} Hevy routines."


async def _workouts(settings: Settings, args: argparse.Namespace) -> str:
    async with _client(settings) as client:
        workouts = await client.get_recent_workouts(args.limit)
    return f"Downloaded {len(workouts)} recent Hevy workouts."


async def _templates(settings: Settings, _: argparse.Namespace) -> str:
    async with _client(settings) as client:
        templates = await client.get_all_exercise_templates()
    return f"Downloaded {len(templates)} Hevy exercise templates."


async def _sync(settings: Settings, _: argparse.Namespace) -> str:
    engine = create_engine(settings.database_url)
    try:
        async with _client(settings) as client:
            result = await HevySyncService(client, create_session_factory(engine)).sync()
    finally:
        await engine.dispose()
    counts = result.counts
    return (
        f"Synchronized Hevy (run {result.run_id}): inserted={counts.inserted}, "
        f"updated={counts.updated}, unchanged={counts.unchanged}, deleted={counts.deleted}."
    )


async def _poll_hevy_automation(settings: Settings, _: argparse.Namespace) -> str:
    engine = create_engine(settings.database_url)
    try:
        async with _client(settings) as client:
            gate = await WorkoutReviewAutomationService(
                client, create_session_factory(engine)
            ).poll()
    finally:
        await engine.dispose()
    if not gate.wake_agent:
        return json.dumps({"wakeAgent": False})
    return json.dumps(
        {
            "wakeAgent": True,
            "context": {
                "review_id": str(gate.review_id),
                "workout_id": gate.workout_id,
            },
        }
    )


async def _metrics_summary(settings: Settings, args: argparse.Namespace) -> str:
    engine = create_engine(settings.database_url)
    try:
        summary = await MetricsService(create_session_factory(engine)).summary(
            as_of=datetime.now(UTC),
            window_days=args.days,
            target_sessions_per_week=Decimal(str(args.target_sessions)),
            stagnation_rule=StagnationRule(
                lookback_sessions=args.stagnation_sessions,
                minimum_sessions=min(4, args.stagnation_sessions),
            ),
        )
    finally:
        await engine.dispose()
    return json.dumps(asdict(summary), default=_json_default, indent=2)


async def _metrics_exercise(settings: Settings, args: argparse.Namespace) -> str:
    engine = create_engine(settings.database_url)
    try:
        report = await MetricsService(create_session_factory(engine)).exercise_report(
            args.exercise_template_id,
            as_of=datetime.now(UTC),
            window_days=args.days,
        )
    finally:
        await engine.dispose()
    return json.dumps(asdict(report), default=_json_default, indent=2)


async def _coach_profile_set(settings: Settings, args: argparse.Namespace) -> str:
    engine = create_engine(settings.database_url)
    try:
        profile = await CoachManagementService(create_session_factory(engine)).set_profile(
            AthleteProfileInput(
                experience_level=args.experience,
                training_days_per_week=args.days,
                session_duration_minutes=args.minutes,
                equipment=args.equipment,
                limitations=args.limitation,
                preferences=args.preference,
            )
        )
    finally:
        await engine.dispose()
    return f"Athlete profile saved ({profile.training_days_per_week} training days/week)."


async def _coach_goal_add(settings: Settings, args: argparse.Namespace) -> str:
    engine = create_engine(settings.database_url)
    try:
        goal = await CoachManagementService(create_session_factory(engine)).add_goal(
            TrainingGoalInput(
                goal_type=args.type,
                description=args.description,
                priority=args.priority,
                target_date=date.fromisoformat(args.target_date) if args.target_date else None,
            )
        )
    finally:
        await engine.dispose()
    return f"Training goal v{goal.version} saved ({goal.goal_type})."


async def _coach_ask(settings: Settings, args: argparse.Namespace) -> str:
    try:
        from gym_coach.coach.service import CoachService
        from gym_coach.integrations.models import build_coach_model
    except ModuleNotFoundError as exc:
        raise CoachError(
            "The experimental PydanticAI coach is not installed; "
            "run `uv sync --extra pydanticai` to enable it"
        ) from exc
    engine = create_engine(settings.database_url)
    try:
        configured_model = build_coach_model(settings)
        result = await CoachService(
            create_session_factory(engine),
            model=configured_model.model,
            model_name=configured_model.name,
        ).ask(args.request)
    finally:
        await engine.dispose()
    output: dict[str, object] = {
        "answer": result.response.answer,
        "evidence_ids": result.response.evidence_ids,
    }
    output["findings"] = [item.model_dump(mode="json") for item in result.response.findings]
    if result.response.proposal is not None:
        output["proposal"] = result.response.proposal.model_dump(mode="json")
    if result.stored_proposal is not None:
        output["proposal_record"] = result.stored_proposal.model_dump(mode="json")
        output["notice"] = "Draft only: approval does not modify Hevy."
    return json.dumps(output, indent=2, ensure_ascii=False)


async def _coach_proposals(settings: Settings, _: argparse.Namespace) -> str:
    engine = create_engine(settings.database_url)
    try:
        proposals = await CoachManagementService(create_session_factory(engine)).list_proposals()
    finally:
        await engine.dispose()
    return json.dumps(
        [item.model_dump(mode="json") for item in proposals], indent=2, ensure_ascii=False
    )


async def _coach_decide(settings: Settings, args: argparse.Namespace) -> str:
    engine = create_engine(settings.database_url)
    try:
        proposal = await CoachManagementService(create_session_factory(engine)).decide(
            UUID(args.proposal_id), args.decision
        )
    finally:
        await engine.dispose()
    return f"Proposal {proposal.id} marked {proposal.status}. No routine was modified in Hevy."


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported JSON output type: {type(value).__name__}")


Handler = Callable[[Settings, argparse.Namespace], Coroutine[Any, Any, str]]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gym-coach")
    groups = parser.add_subparsers(dest="group", required=True)
    mcp = groups.add_parser("mcp", help="Run the controlled local MCP server over stdio")
    mcp.set_defaults(run_mcp=True)
    hevy = groups.add_parser("hevy", help="Read-only Hevy operations")
    commands = hevy.add_subparsers(dest="command", required=True)
    handlers: dict[str, Handler] = {
        "check": _check,
        "user": _user,
        "routines": _routines,
        "workouts": _workouts,
        "exercise-templates": _templates,
        "sync": _sync,
    }
    for name, handler in handlers.items():
        command = commands.add_parser(name)
        command.set_defaults(handler=handler)
        if name == "workouts":
            command.add_argument("--limit", type=int, default=10)
    automation = groups.add_parser("automation", help="Controlled background automation")
    automation_commands = automation.add_subparsers(dest="command", required=True)
    poll_hevy = automation_commands.add_parser(
        "poll-hevy", help="Poll workout events and gate an automatic review"
    )
    poll_hevy.set_defaults(handler=_poll_hevy_automation)
    metrics = groups.add_parser("metrics", help="Deterministic sports metrics")
    metric_commands = metrics.add_subparsers(dest="command", required=True)
    summary = metric_commands.add_parser("summary")
    summary.set_defaults(handler=_metrics_summary)
    summary.add_argument("--days", type=int, default=28)
    summary.add_argument("--target-sessions", type=float, default=4.0)
    summary.add_argument("--stagnation-sessions", type=int, default=6)
    exercise = metric_commands.add_parser("exercise")
    exercise.set_defaults(handler=_metrics_exercise)
    exercise.add_argument("exercise_template_id")
    exercise.add_argument("--days", type=int, default=180)
    coach = groups.add_parser("coach", help="Personal coach and local proposals")
    coach_commands = coach.add_subparsers(dest="command", required=True)
    profile = coach_commands.add_parser("profile-set")
    profile.set_defaults(handler=_coach_profile_set)
    profile.add_argument(
        "--experience", choices=("beginner", "intermediate", "advanced"), required=True
    )
    profile.add_argument("--days", type=int, required=True)
    profile.add_argument("--minutes", type=int)
    profile.add_argument("--equipment", action="append", default=[])
    profile.add_argument("--limitation", action="append", default=[])
    profile.add_argument("--preference", action="append", default=[])
    goal = coach_commands.add_parser("goal-add")
    goal.set_defaults(handler=_coach_goal_add)
    goal.add_argument(
        "--type",
        choices=("strength", "hypertrophy", "endurance", "health", "skill", "other"),
        required=True,
    )
    goal.add_argument("--description", required=True)
    goal.add_argument("--priority", type=int, default=1)
    goal.add_argument("--target-date")
    ask = coach_commands.add_parser("ask")
    ask.set_defaults(handler=_coach_ask)
    ask.add_argument("request")
    proposals = coach_commands.add_parser("proposals")
    proposals.set_defaults(handler=_coach_proposals)
    for decision in ("approve", "reject"):
        command = coach_commands.add_parser(decision)
        command.set_defaults(
            handler=_coach_decide,
            decision="approved" if decision == "approve" else "rejected",
        )
        command.add_argument("proposal_id")
    return parser


def main() -> None:
    args = _parser().parse_args()
    if getattr(args, "run_mcp", False):
        run_stdio_server(get_settings())
        return
    handler: Handler = args.handler
    try:
        message: str = asyncio.run(handler(get_settings(), args))
    except (CoachError, HevyError, HevySyncError, MetricsError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    print(message)


if __name__ == "__main__":
    main()
