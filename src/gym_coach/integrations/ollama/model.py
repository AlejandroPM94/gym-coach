from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.settings import ModelSettings

from gym_coach.config import Settings


def build_ollama_model(settings: Settings) -> OpenAIChatModel:
    return OpenAIChatModel(
        settings.ollama_model,
        provider=OllamaProvider(base_url=settings.ollama_base_url),
        settings=ModelSettings(max_tokens=6000, timeout=300),
    )
