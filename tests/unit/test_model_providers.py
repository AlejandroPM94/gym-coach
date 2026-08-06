import pytest

from gym_coach.coach.errors import CoachConfigurationError
from gym_coach.config import Settings
from gym_coach.integrations.models import build_coach_model


def test_ollama_is_the_default_free_provider() -> None:
    configured = build_coach_model(Settings(_env_file=None))

    assert configured.name == "ollama:gpt-oss:20b"


def test_openai_remains_optional_and_requires_a_key() -> None:
    settings = Settings(_env_file=None, GYM_COACH_PROVIDER="openai")

    with pytest.raises(CoachConfigurationError, match="OPENAI_API_KEY"):
        build_coach_model(settings)
