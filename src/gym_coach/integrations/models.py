from dataclasses import dataclass

from pydantic_ai.models import Model

from gym_coach.config import Settings
from gym_coach.integrations.ollama.model import build_ollama_model
from gym_coach.integrations.openai.model import build_openai_model


@dataclass(frozen=True, slots=True)
class ConfiguredModel:
    model: Model
    name: str


def build_coach_model(settings: Settings) -> ConfiguredModel:
    if settings.coach_provider == "ollama":
        return ConfiguredModel(
            model=build_ollama_model(settings),
            name=f"ollama:{settings.ollama_model}",
        )
    return ConfiguredModel(
        model=build_openai_model(settings),
        name=f"openai:{settings.openai_model}",
    )
