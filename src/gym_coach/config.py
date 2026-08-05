from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = Field(
        default="development", alias="GYM_COACH_ENVIRONMENT"
    )
    log_level: str = Field(default="INFO", alias="GYM_COACH_LOG_LEVEL")
    database_url: str = Field(
        default="postgresql+psycopg://gym_coach:gym_coach@localhost:5432/gym_coach",
        alias="GYM_COACH_DATABASE_URL",
    )
    hevy_api_key: SecretStr | None = Field(default=None, alias="HEVY_API_KEY")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.6-terra", alias="GYM_COACH_OPENAI_MODEL")
    openai_reasoning_effort: Literal["low", "medium", "high"] = Field(
        default="medium", alias="GYM_COACH_OPENAI_REASONING_EFFORT"
    )
    hevy_base_url: str = Field(default="https://api.hevyapp.com", alias="GYM_COACH_HEVY_BASE_URL")
    hevy_timeout_seconds: float = Field(default=15.0, gt=0, alias="GYM_COACH_HEVY_TIMEOUT_SECONDS")
    hevy_retry_attempts: int = Field(default=3, ge=1, le=10, alias="GYM_COACH_HEVY_RETRY_ATTEMPTS")
    hevy_retry_backoff_seconds: float = Field(
        default=0.5, ge=0, le=30, alias="GYM_COACH_HEVY_RETRY_BACKOFF_SECONDS"
    )
    raw_data_dir: Path = Field(default=Path("data/raw/hevy"), alias="GYM_COACH_RAW_DATA_DIR")


@lru_cache
def get_settings() -> Settings:
    return Settings()
