from typing import Annotated, Literal

from annotated_types import Ge, Le
from pydantic import HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    log_level: LogLevel = "INFO"

    openai_api_key: SecretStr
    sentiment_model: str = "gpt5.4-nano"

    tracked_x_account: HttpUrl

    min_confidence: Annotated[float, Ge(0.0), Le(1.0)] = 0.7
    max_order_amount_usd: Annotated[float, Ge(0.0)] = 100.0


def load_settings() -> Settings:
    return Settings()
