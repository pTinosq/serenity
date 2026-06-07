"""Interactive settings editor backed by gum.

Reads and writes `.env` directly via python-dotenv. Validates each new
value against the field's annotation on `Settings` (including any
metadata like Ge/Le) before writing, so an invalid input never lands
in the file.
"""

from pathlib import Path
from typing import Annotated, Any, Literal, get_args, get_origin

from dotenv import dotenv_values, set_key
from pydantic import TypeAdapter, ValidationError

from serenity.config import Settings
from serenity.ui import gum

FIELDS: list[tuple[str, str]] = [
    ("log_level", "LOG_LEVEL"),
    ("openrouter_api_key", "OPENROUTER_API_KEY"),
    ("sentiment_model", "SENTIMENT_MODEL"),
    ("tracked_x_account", "TRACKED_X_ACCOUNT"),
    ("x_bearer_token", "X_BEARER_TOKEN"),
    ("min_confidence", "MIN_CONFIDENCE"),
    ("min_trade_usd", "MIN_TRADE_USD"),
    ("max_trade_usd", "MAX_TRADE_USD"),
    ("max_trades_per_day", "MAX_TRADES_PER_DAY"),
    ("alpaca_api_key", "ALPACA_API_KEY"),
    ("alpaca_secret_key", "ALPACA_SECRET_KEY"),
    ("alpaca_paper", "ALPACA_PAPER"),
    ("alert_fallback_channel", "ALERT_FALLBACK_CHANNEL"),
    ("telegram_bot_token", "TELEGRAM_BOT_TOKEN"),
    ("telegram_chat_id", "TELEGRAM_CHAT_ID"),
    ("message_frequency", "MESSAGE_FREQUENCY"),
    ("daily_message_delivery_utc", "DAILY_MESSAGE_DELIVERY_UTC"),
]

SECRET_FIELDS = {
    "openrouter_api_key",
    "x_bearer_token",
    "alpaca_api_key",
    "alpaca_secret_key",
    "telegram_bot_token",
}

KEY_COL = max(len(env_var) for _, env_var in FIELDS)
BACK = "← Back"

ENV_FILE = Path(Settings.model_config.get("env_file") or ".env")


def mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return "•" * len(value)
    return value[:3] + "•" * (len(value) - 6) + value[-3:]


def display_value(field_name: str, value: str) -> str:
    if not value:
        return "(unset)"
    if field_name in SECRET_FIELDS:
        return mask(value)
    return value


def format_row(env_var: str, display: str) -> str:
    return f"{env_var.ljust(KEY_COL)}   {display}"


def validate(field_name: str, raw: str) -> str | None:
    """Return an error message if `raw` is invalid for `field_name`, else None."""
    field = Settings.model_fields[field_name]
    annotation = (
        Annotated[(field.annotation, *field.metadata)]
        if field.metadata
        else field.annotation
    )
    try:
        TypeAdapter(annotation).validate_python(raw)
    except ValidationError as e:
        return e.errors()[0].get("msg", str(e))
    return None


def literal_choices(annotation: Any) -> tuple[str, ...] | None:
    """If `annotation` is a Literal[...] of strings, return its choices."""
    if get_origin(annotation) is Literal:
        args = get_args(annotation)
        if all(isinstance(a, str) for a in args):
            return args
    return None


def prompt_new_value(field_name: str, env_var: str, current: str) -> str | None:
    """Pick the right gum widget for the field's type and return the raw input."""
    annotation = Settings.model_fields[field_name].annotation

    choices = literal_choices(annotation)
    if choices is not None:
        return gum.choose(
            *choices,
            header=f"{env_var} — pick a value",
            selected=current or None,
        )

    if annotation is bool:
        return gum.choose(
            "True",
            "False",
            header=f"{env_var} — pick a value",
            selected=current or None,
        )

    is_secret = field_name in SECRET_FIELDS
    return gum.ask(
        prompt=f"{env_var}: ",
        value="" if is_secret else current,
        placeholder="paste new value" if is_secret else "",
        password=is_secret,
    )


def edit_field(field_name: str, env_var: str, current: str) -> None:
    try:
        new_value = prompt_new_value(field_name, env_var, current)
    except KeyboardInterrupt:
        return

    new_value = new_value.strip()
    if not new_value or new_value == current:
        return

    error = validate(field_name, new_value)
    if error:
        gum.style(f"  ✗ {env_var}: {error}", foreground="9", bold=True)
        return

    ENV_FILE.touch(exist_ok=True)
    set_key(str(ENV_FILE), env_var, new_value, quote_mode="never")
    gum.style(f"  ✓ {env_var} updated", foreground="10")


def open_settings() -> None:
    """Top-level entry point: loop showing the settings list."""
    while True:
        values = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
        rows = [
            format_row(env_var, display_value(field_name, values.get(env_var, "")))
            for field_name, env_var in FIELDS
        ]
        rows.append(BACK)

        try:
            choice = gum.choose(*rows, header="Settings — pick one to edit")
        except KeyboardInterrupt:
            return

        if choice == BACK or not choice:
            return

        chosen_env_var = choice.split()[0] if choice else ""
        for field_name, env_var in FIELDS:
            if env_var == chosen_env_var:
                edit_field(field_name, env_var, values.get(env_var, ""))
                break
