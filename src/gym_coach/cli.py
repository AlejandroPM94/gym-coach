import argparse
import asyncio
import sys
from collections.abc import Callable, Coroutine
from typing import Any

from gym_coach.config import Settings, get_settings
from gym_coach.integrations.hevy.client import HevyClient
from gym_coach.integrations.hevy.errors import HevyConfigurationError, HevyError
from gym_coach.integrations.hevy.raw_store import RawResponseStore


def _client(settings: Settings) -> HevyClient:
    if settings.hevy_api_key is None or not settings.hevy_api_key.get_secret_value():
        raise HevyConfigurationError("HEVY_API_KEY is not configured; add it to your local .env")
    return HevyClient(
        settings.hevy_api_key,
        base_url=settings.hevy_base_url,
        timeout_seconds=settings.hevy_timeout_seconds,
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


Handler = Callable[[Settings, argparse.Namespace], Coroutine[Any, Any, str]]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gym-coach")
    groups = parser.add_subparsers(dest="group", required=True)
    hevy = groups.add_parser("hevy", help="Read-only Hevy operations")
    commands = hevy.add_subparsers(dest="command", required=True)
    handlers: dict[str, Handler] = {
        "check": _check,
        "user": _user,
        "routines": _routines,
        "workouts": _workouts,
        "exercise-templates": _templates,
    }
    for name, handler in handlers.items():
        command = commands.add_parser(name)
        command.set_defaults(handler=handler)
        if name == "workouts":
            command.add_argument("--limit", type=int, default=10)
    return parser


def main() -> None:
    args = _parser().parse_args()
    handler: Handler = args.handler
    try:
        message: str = asyncio.run(handler(get_settings(), args))
    except (HevyError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    print(message)


if __name__ == "__main__":
    main()
