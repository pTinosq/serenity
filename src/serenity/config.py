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

    openrouter_api_key: SecretStr
    sentiment_model: str = "openai/gpt-5.4-nano"

    tracked_x_account: HttpUrl
    x_bearer_token: SecretStr

    min_confidence: Annotated[float, Ge(0.0), Le(1.0)] = 0.7
    min_trade_usd: Annotated[float, Ge(0.0)] = 10.0
    max_trade_usd: Annotated[float, Ge(0.0)] = 100.0

    alpaca_api_key: SecretStr | None = None
    alpaca_secret_key: SecretStr | None = None
    alpaca_paper: bool = True

    alert_fallback_channel: Literal["stdout", "telegram"] = "stdout"
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None


def load_settings() -> Settings:
    return Settings()
