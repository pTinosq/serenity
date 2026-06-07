"""Interactive `.env` wizard.

Walks new users through the minimum config needed to run Serenity,
section by section. Designed to be safe to re-run: any field already
present in `.env` is kept untouched, so re-running after a release
that introduces new settings only prompts for the new (blank) fields.

To change an existing value, use the `Settings` entry in the main menu
(`serenity` without `--headless`) rather than this wizard — the wizard
is the "fill in what's missing" tool.

Conditional sections only ask for what you actually need: Alpaca is
opt-in; Telegram fields appear only when you pick the telegram
channel; the daily-delivery time appears only when you pick the
daily frequency.

Lives under `serenity.cli` because it's a developer / setup tool, not
a runtime feature. Invoked via `just init`.
"""

from dotenv import dotenv_values, set_key

from serenity.ui import gum
from serenity.ui.settings import ENV_FILE, prompt_new_value, validate


def write(env_var: str, value: str) -> None:
    ENV_FILE.touch(exist_ok=True)
    set_key(str(ENV_FILE), env_var, value, quote_mode="never")


def ask(
    field_name: str,
    env_var: str,
    current: str = "",
    *,
    default: str = "",
    required: bool = False,
) -> str:
    """Prompt for `field_name`, validate, write to `.env`.

    If `current` already has a value (i.e. the env var is set in `.env`),
    keep it and return without prompting — running the wizard a second
    time should be a fast pass to fill in newly-added settings, not a
    full re-entry.

    Otherwise prompt with `default` as the prefill. Returns the saved
    value (or `default` if a non-required field is left blank and a
    default was supplied).

    KeyboardInterrupt propagates — the top-level wizard catches it and
    exits gracefully, treating Esc/Ctrl-C as "stop here, keep whatever
    was already written".
    """
    if current:
        gum.style(f"  ✓ {env_var}: kept (Settings menu to change)", foreground="8")
        return current

    while True:
        raw = (prompt_new_value(field_name, env_var, default) or "").strip()
        if not raw:
            if required:
                gum.style(f"  ✗ {env_var} is required", foreground="9", bold=True)
                continue
            # Optional and blank: write the default if we had one, else nothing.
            if default:
                write(env_var, default)
                gum.style(f"  ✓ {env_var}: {default} (default)", foreground="10")
                return default
            return ""
        err = validate(field_name, raw)
        if err:
            gum.style(f"  ✗ {env_var}: {err}", foreground="9", bold=True)
            continue
        write(env_var, raw)
        gum.style(f"  ✓ {env_var}", foreground="10")
        return raw


def section(step: str, title: str, blurb: str) -> None:
    print()
    gum.style(f"━━━ {step} — {title} ━━━", foreground="14", bold=True)
    gum.style(blurb, foreground="8")
    print()


def main() -> None:
    try:
        run()
    except KeyboardInterrupt:
        print()
        gum.style("Aborted. Partial progress saved to .env.", foreground="8")


def run() -> None:
    print()
    gum.style("Serenity Setup", foreground="14", bold=True)
    gum.style(
        f"Writing to {ENV_FILE}. Fields already in .env are kept; the "
        "wizard only asks for what's missing. Use the Settings menu "
        "(`serenity`) to change existing values. Esc/Ctrl-C aborts.",
        foreground="8",
    )

    existing = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    cur = lambda k: existing.get(k, "")  # noqa: E731

    section("Step 1/5", "Required keys", "Without these the bot won't start.")
    ask("openrouter_api_key", "OPENROUTER_API_KEY", cur("OPENROUTER_API_KEY"), required=True)
    ask("x_bearer_token", "X_BEARER_TOKEN", cur("X_BEARER_TOKEN"), required=True)
    ask("tracked_x_account", "TRACKED_X_ACCOUNT", cur("TRACKED_X_ACCOUNT"), required=True)

    section(
        "Step 2/5",
        "Oracle & logging",
        "Defaults work for most users.",
    )
    ask("sentiment_model", "SENTIMENT_MODEL", cur("SENTIMENT_MODEL"), default="google/gemini-2.5-flash")
    ask("log_level", "LOG_LEVEL", cur("LOG_LEVEL"), default="INFO")

    section(
        "Step 3/5",
        "Trading",
        "Per-trade sizing, risk caps, and (optional) Alpaca credentials. "
        "Per-trade notional is sentiment * MAX_TRADE_USD, clamped to "
        "[MIN, MAX] and to available cash. The runner enforces the "
        "position and daily caps as hard limits — set to 0 to disable.",
    )
    ask("min_confidence", "MIN_CONFIDENCE", cur("MIN_CONFIDENCE"), default="0.7")
    ask("min_trade_usd", "MIN_TRADE_USD", cur("MIN_TRADE_USD"), default="10.0")
    ask("max_trade_usd", "MAX_TRADE_USD", cur("MAX_TRADE_USD"), default="100.0")
    ask("max_position_usd", "MAX_POSITION_USD", cur("MAX_POSITION_USD"), default="500.0")
    ask("max_trades_per_day", "MAX_TRADES_PER_DAY", cur("MAX_TRADES_PER_DAY"), default="20")

    alpaca_already_set = bool(cur("ALPACA_API_KEY") and cur("ALPACA_SECRET_KEY"))
    if alpaca_already_set or gum.confirm("Set up Alpaca credentials now?"):
        ask("alpaca_api_key", "ALPACA_API_KEY", cur("ALPACA_API_KEY"), required=True)
        ask("alpaca_secret_key", "ALPACA_SECRET_KEY", cur("ALPACA_SECRET_KEY"), required=True)
        ask("alpaca_paper", "ALPACA_PAPER", cur("ALPACA_PAPER"), default="True")

    section("Step 4/5", "Alerts", "Where event notifications get delivered.")
    channel = ask(
        "alert_fallback_channel",
        "ALERT_FALLBACK_CHANNEL",
        cur("ALERT_FALLBACK_CHANNEL"),
        default="stdout",
        required=True,
    )
    if channel == "telegram":
        gum.style(
            "  Create a bot via @BotFather, DM it any message, then visit",
            foreground="8",
        )
        gum.style(
            "  https://api.telegram.org/bot<TOKEN>/getUpdates and copy chat.id.",
            foreground="8",
        )
        ask("telegram_bot_token", "TELEGRAM_BOT_TOKEN", cur("TELEGRAM_BOT_TOKEN"), required=True)
        ask("telegram_chat_id", "TELEGRAM_CHAT_ID", cur("TELEGRAM_CHAT_ID"), required=True)

    section("Step 5/5", "Frequency", "How often the bot pings you.")
    freq = ask(
        "message_frequency",
        "MESSAGE_FREQUENCY",
        cur("MESSAGE_FREQUENCY"),
        default="per-tweet",
        required=True,
    )
    if freq == "daily":
        ask(
            "daily_message_delivery_utc",
            "DAILY_MESSAGE_DELIVERY_UTC",
            cur("DAILY_MESSAGE_DELIVERY_UTC"),
            default="21:30",
            required=True,
        )

    print()
    gum.style("✓ Done. Run `just start` to launch.", foreground="10", bold=True)


if __name__ == "__main__":
    main()
