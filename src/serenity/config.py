from typing import Annotated, Literal

from annotated_types import Ge, Le
from pydantic import HttpUrl, SecretStr, StringConstraints
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
    sentiment_model: str = "google/gemini-2.5-flash"

    tracked_x_account: HttpUrl
    x_bearer_token: SecretStr

    min_confidence: Annotated[float, Ge(0.0), Le(1.0)] = 0.7
    min_trade_usd: Annotated[float, Ge(0.0)] = 10.0
    max_trade_usd: Annotated[float, Ge(0.0)] = 100.0
    max_position_usd: Annotated[float, Ge(0.0)] = 500.0
    max_trades_per_day: Annotated[int, Ge(0)] = 20

    alpaca_api_key: SecretStr | None = None
    alpaca_secret_key: SecretStr | None = None
    alpaca_paper: bool = True

    alert_fallback_channel: Literal["stdout", "telegram"] = "stdout"
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None

    message_frequency: Literal["per-tweet", "daily"] = "per-tweet"
    daily_message_delivery_utc: Annotated[
        str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    ] = "21:30"
    # Where the daily-mode JSONL buffer lives. On Railway the working
    # directory may not be writable; in that case override to e.g.
    # `/tmp/serenity/event_log.jsonl` (ephemeral) or a mounted volume
    # path like `/data/event_log.jsonl` (persistent across restarts).
    event_log_path: str = "data/event_log.jsonl"


def load_settings() -> Settings:
    return Settings()
