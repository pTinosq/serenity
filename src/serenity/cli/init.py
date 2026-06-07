"""Interactive `.env` wizard.

Walks new users through the minimum config needed to run Serenity,
section by section. Re-running picks up existing `.env` values as
defaults, so it's safe to run repeatedly to refine setup.

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
    required: bool = False,
) -> str:
    """Prompt for `field_name`, validate, write to `.env`. Loop on bad input.

    Returns the saved value, or "" if the user left a non-required
    field blank. KeyboardInterrupt propagates — the top-level wizard
    catches it and exits gracefully, treating Esc/Ctrl-C as "stop here,
    keep whatever was already written".
    """
    while True:
        raw = (prompt_new_value(field_name, env_var, current) or "").strip()
        if not raw:
            if required:
                gum.style(f"  ✗ {env_var} is required", foreground="9", bold=True)
                continue
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
    gum.style(f"Writing to {ENV_FILE}. Esc/Ctrl-C aborts; progress is kept.", foreground="8")

    existing = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    get = lambda k, d="": existing.get(k, d)  # noqa: E731

    section("Step 1/5", "Required keys", "Without these the bot won't start.")
    ask("openrouter_api_key", "OPENROUTER_API_KEY", get("OPENROUTER_API_KEY"), required=True)
    ask("x_bearer_token", "X_BEARER_TOKEN", get("X_BEARER_TOKEN"), required=True)
    ask("tracked_x_account", "TRACKED_X_ACCOUNT", get("TRACKED_X_ACCOUNT"), required=True)

    section(
        "Step 2/5",
        "Oracle & logging",
        "Defaults work for most users. Hit Enter to keep them.",
    )
    ask("sentiment_model", "SENTIMENT_MODEL", get("SENTIMENT_MODEL", "google/gemini-2.5-flash"))
    ask("log_level", "LOG_LEVEL", get("LOG_LEVEL", "INFO"))

    section(
        "Step 3/5",
        "Trading",
        "Per-trade sizing and (optional) Alpaca credentials. Notional is "
        "sentiment * MAX, clamped to [MIN, MAX] and to available cash.",
    )
    ask("min_confidence", "MIN_CONFIDENCE", get("MIN_CONFIDENCE", "0.7"))
    ask("min_trade_usd", "MIN_TRADE_USD", get("MIN_TRADE_USD", "10.0"))
    ask("max_trade_usd", "MAX_TRADE_USD", get("MAX_TRADE_USD", "100.0"))
    if gum.confirm("Set up Alpaca credentials now?"):
        ask("alpaca_api_key", "ALPACA_API_KEY", get("ALPACA_API_KEY"), required=True)
        ask("alpaca_secret_key", "ALPACA_SECRET_KEY", get("ALPACA_SECRET_KEY"), required=True)
        ask("alpaca_paper", "ALPACA_PAPER", get("ALPACA_PAPER", "True"))

    section("Step 4/5", "Alerts", "Where event notifications get delivered.")
    channel = ask(
        "alert_fallback_channel",
        "ALERT_FALLBACK_CHANNEL",
        get("ALERT_FALLBACK_CHANNEL", "stdout"),
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
        ask("telegram_bot_token", "TELEGRAM_BOT_TOKEN", get("TELEGRAM_BOT_TOKEN"), required=True)
        ask("telegram_chat_id", "TELEGRAM_CHAT_ID", get("TELEGRAM_CHAT_ID"), required=True)

    section("Step 5/5", "Frequency", "How often the bot pings you.")
    freq = ask(
        "message_frequency",
        "MESSAGE_FREQUENCY",
        get("MESSAGE_FREQUENCY", "per-tweet"),
        required=True,
    )
    if freq == "daily":
        ask(
            "daily_message_delivery_utc",
            "DAILY_MESSAGE_DELIVERY_UTC",
            get("DAILY_MESSAGE_DELIVERY_UTC", "21:30"),
            required=True,
        )

    print()
    gum.style("✓ Done. Run `just start` to launch.", foreground="10", bold=True)


if __name__ == "__main__":
    main()
