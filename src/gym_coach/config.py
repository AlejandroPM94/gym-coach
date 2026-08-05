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
    hevy_base_url: str = Field(default="https://api.hevyapp.com", alias="GYM_COACH_HEVY_BASE_URL")
    hevy_timeout_seconds: float = Field(default=15.0, gt=0, alias="GYM_COACH_HEVY_TIMEOUT_SECONDS")
    raw_data_dir: Path = Field(default=Path("data/raw/hevy"), alias="GYM_COACH_RAW_DATA_DIR")


@lru_cache
def get_settings() -> Settings:
    return Settings()
