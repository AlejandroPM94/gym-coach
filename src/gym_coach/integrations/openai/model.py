from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

from gym_coach.coach.errors import CoachConfigurationError
from gym_coach.config import Settings


def build_openai_model(settings: Settings) -> OpenAIResponsesModel:
    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
        raise CoachConfigurationError("OPENAI_API_KEY is not configured; add it to your local .env")
    provider = OpenAIProvider(api_key=settings.openai_api_key.get_secret_value())
    return OpenAIResponsesModel(
        settings.openai_model,
        provider=provider,
        settings=OpenAIResponsesModelSettings(
            max_tokens=6000,
            timeout=60,
            openai_reasoning_effort=settings.openai_reasoning_effort,
            openai_store=False,
        ),
    )
