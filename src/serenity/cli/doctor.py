"""Print the effective config the bot is actually seeing.

Settings can come from three places — Railway / shell env vars, the
local `.env` file, and pydantic defaults — and divergence between
what you set in one and what the bot reads is the #1 source of
"why isn't this working?" tickets.

This command resolves the same `load_settings()` the bot uses,
then prints the live values, masks secrets, and flags anything
that's likely surprising (frequency=per-tweet despite a daily
delivery time being set, telegram channel selected without
credentials, etc.).

Invoked via `just doctor`.
"""

import os
import sys
from pathlib import Path

from rich import print as rprint
from rich.panel import Panel
from rich.table import Table

from serenity.config import Settings, load_settings


SECRETS = {
    "OPENROUTER_API_KEY",
    "X_BEARER_TOKEN",
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "TELEGRAM_BOT_TOKEN",
}

# (field_name, env_var) — matches ui/settings.py FIELDS order.
FIELDS = [
    ("log_level", "LOG_LEVEL"),
    ("openrouter_api_key", "OPENROUTER_API_KEY"),
    ("sentiment_model", "SENTIMENT_MODEL"),
    ("tracked_x_account", "TRACKED_X_ACCOUNT"),
    ("x_bearer_token", "X_BEARER_TOKEN"),
    ("min_confidence", "MIN_CONFIDENCE"),
    ("min_trade_usd", "MIN_TRADE_USD"),
    ("max_trade_usd", "MAX_TRADE_USD"),
    ("max_position_usd", "MAX_POSITION_USD"),
    ("max_trades_per_day", "MAX_TRADES_PER_DAY"),
    ("alpaca_api_key", "ALPACA_API_KEY"),
    ("alpaca_secret_key", "ALPACA_SECRET_KEY"),
    ("alpaca_paper", "ALPACA_PAPER"),
    ("alert_fallback_channel", "ALERT_FALLBACK_CHANNEL"),
    ("telegram_bot_token", "TELEGRAM_BOT_TOKEN"),
    ("telegram_chat_id", "TELEGRAM_CHAT_ID"),
    ("message_frequency", "MESSAGE_FREQUENCY"),
    ("daily_message_delivery_utc", "DAILY_MESSAGE_DELIVERY_UTC"),
    ("event_log_path", "EVENT_LOG_PATH"),
]


def mask(value: str) -> str:
    if not value:
        return "(unset)"
    if len(value) <= 6:
        return "•" * len(value)
    return value[:3] + "•" * (len(value) - 6) + value[-3:]


def value_str(settings: Settings, field: str) -> str:
    raw = getattr(settings, field, None)
    if raw is None:
        return "(unset)"
    if hasattr(raw, "get_secret_value"):
        return mask(raw.get_secret_value())
    return str(raw)


def source_of(env_var: str) -> str:
    """Where did this value most likely come from?"""
    if env_var in os.environ:
        return "env"
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{env_var}="):
                return ".env"
    return "default"


def buffer_probe(settings: Settings) -> str | None:
    """Try to write+read the event log path; return None on success or a reason on failure."""
    if settings.message_frequency != "daily":
        return None
    p = Path(settings.event_log_path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        probe = p.parent / ".serenity-buffer-probe"
        probe.write_text("ok", encoding="utf-8")
        content = probe.read_text(encoding="utf-8")
        probe.unlink()
        if content != "ok":
            return f"wrote 'ok' to {probe} but read back {content!r}"
    except Exception as e:
        return f"{type(e).__name__}: {e} (path={p.absolute()})"
    return None


def warnings(settings: Settings) -> list[str]:
    out: list[str] = []
    if settings.alert_fallback_channel == "telegram":
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            out.append(
                "ALERT_FALLBACK_CHANNEL=telegram but credentials are missing — "
                "alerts will fall back to stdout at runtime."
            )
    if settings.message_frequency == "daily":
        probe_err = buffer_probe(settings)
        if probe_err is None:
            out.append(
                "message_frequency=daily: buffer probe OK at "
                f"{Path(settings.event_log_path).absolute()}. Alerts will be "
                f"buffered until {settings.daily_message_delivery_utc} UTC."
            )
        else:
            out.append(
                "message_frequency=daily BUT buffer probe FAILED: "
                f"{probe_err}. Daily-mode buffering will be broken — every "
                "Alert ships per-tweet. Set EVENT_LOG_PATH to a writable "
                "location (e.g. /tmp/serenity/event_log.jsonl) and redeploy."
            )
    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        out.append("Alpaca credentials missing — bot will skip the trading stage.")
    return out


def main() -> None:
    try:
        settings = load_settings()
    except Exception as e:
        rprint(f"[red]load_settings() failed:[/] {e}")
        sys.exit(1)

    rprint(
        Panel.fit(
            f"CWD: {Path.cwd()}\n"
            f".env exists: {Path('.env').exists()}\n"
            f"data/ exists: {Path('data').exists()}",
            title="Environment",
            border_style="cyan",
        )
    )

    table = Table(title="Effective settings")
    table.add_column("Field")
    table.add_column("Value")
    table.add_column("Source", style="dim")

    for field, env_var in FIELDS:
        table.add_row(env_var, value_str(settings, field), source_of(env_var))
    rprint(table)

    issues = warnings(settings)
    if issues:
        rprint("\n[yellow]Notes:[/]")
        for w in issues:
            rprint(f"  • {w}")
    else:
        rprint("\n[green]No surprising config.[/]")


if __name__ == "__main__":
    main()
