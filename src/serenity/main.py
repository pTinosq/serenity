import argparse
import logging

from serenity.alerts import Alert, Messenger, notify_crash
from serenity.alerts.scheduler import start_daily_scheduler
from serenity.config import Settings, load_settings
from serenity.executor import TradeExecutor, TradeExecutorError, apply_plan
from serenity.logging_config import setup_logging
from serenity.oracle.oracle import Oracle, OracleError
from serenity.portfolio import fetch_portfolio
from serenity.trading import get_client
from serenity.twitter import stream_tweets
from serenity.ui.menu import run_menu

log = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="serenity")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Skip the interactive menu and start the bot directly.",
    )
    return parser.parse_args(argv)


def handle_tweet(
    tweet: str,
    *,
    settings: Settings,
    oracle: Oracle,
    executor: TradeExecutor,
) -> None:
    """Single-tweet pipeline: Oracle → executor → runner.

    Errors raised here are caught by `start_bot`; this function only
    returns normally or raises. Per-tweet failures should be logged
    and absorbed (not raised) so the stream keeps flowing.
    """
    try:
        signal = oracle.analyze(tweet)
    except OracleError:
        log.exception("Oracle failed on tweet")
        return
    log.info("Signal: %s", signal.model_dump())

    if signal.order_type == "N/A":
        log.info("Skipping: no actionable signal")
        return
    if signal.confidence < settings.min_confidence:
        log.info(
            "Skipping %s: confidence %.2f < %.2f",
            signal.ticker, signal.confidence, settings.min_confidence,
        )
        return

    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        log.warning(
            "Skipping %s: Alpaca credentials not configured", signal.ticker,
        )
        return

    client = get_client()
    try:
        cash = float(client.get_account().cash)
        positions = fetch_portfolio(client)
    except Exception:
        log.exception("Failed to fetch account state from Alpaca")
        return

    try:
        plan = executor.decide(
            tweet=tweet, signal=signal, positions=positions, available_cash=cash,
        )
    except TradeExecutorError:
        log.exception("Executor failed on signal")
        return
    log.info("Plan: %s", plan.model_dump())

    outcomes = apply_plan(client, settings, plan, available_cash=cash)
    for outcome in outcomes:
        log.info(
            "Action %s %s -> %s%s",
            outcome.action.action,
            outcome.action.ticker,
            outcome.outcome.value,
            f" ({outcome.detail})" if outcome.detail else "",
        )
        if outcome.outcome.value == "executed":
            Messenger.send(Alert(
                reason="trade_executed",
                title=f"{outcome.action.action} {outcome.action.ticker} — {outcome.detail}",
                signal=signal,
                amount=outcome.submitted_notional,
                tweet=tweet,
            ))
        elif outcome.outcome.value.startswith("skipped"):
            Messenger.send(Alert(
                reason=outcome.outcome.value,
                title=f"{outcome.action.action} {outcome.action.ticker} skipped: {outcome.detail}",
                signal=signal,
                tweet=tweet,
                detail=outcome.action.reasoning,
            ))


def start_bot() -> None:
    """Stream tweets → Oracle → TradeExecutor → runner.

    Per-tweet failures are logged inside `handle_tweet` and the loop
    continues. Anything else — credit exhaustion, revoked tokens,
    upstream outages — propagates here, where we fire a system alert
    before letting the process die so Railway can restart us.
    """
    log.info("Starting [bold cyan]serenity[/] :sparkles:")
    try:
        settings = load_settings()
        oracle = Oracle(settings=settings)
        executor = TradeExecutor(settings=settings)

        if settings.message_frequency == "daily":
            start_daily_scheduler(settings.daily_message_delivery_utc)

        for tweet in stream_tweets(settings):
            log.info("Tweet: %s", tweet[:120].replace("\n", " "))
            handle_tweet(tweet, settings=settings, oracle=oracle, executor=executor)
    except Exception as exc:
        log.exception("Bot loop crashed")
        notify_crash(exc, where="bot loop")
        raise


def main() -> None:
    args = parse_args()
    settings = load_settings()
    setup_logging(settings.log_level)

    if args.headless:
        start_bot()
        return

    run_menu(on_start=start_bot)


if __name__ == "__main__":
    main()
