import argparse
import logging

from serenity.alerts import notify_crash
from serenity.alerts.scheduler import start_daily_scheduler
from serenity.config import load_settings
from serenity.logging_config import setup_logging
from serenity.oracle.oracle import Oracle, OracleError
from serenity.trading import TradingError, execute_trade
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


def start_bot() -> None:
    """Stream tweets → Oracle → Trading.

    Per-tweet failures (Oracle parse errors, Alpaca rejections) are
    logged and the loop continues. Anything else — credit exhaustion,
    revoked tokens, upstream outages — propagates here, where we fire
    a system alert before letting the process die so Railway can
    restart us.
    """
    log.info("Starting [bold cyan]serenity[/] :sparkles:")
    try:
        settings = load_settings()
        oracle = Oracle(settings=settings)

        if settings.message_frequency == "daily":
            start_daily_scheduler(settings.daily_message_delivery_utc)

        for tweet in stream_tweets(settings):
            log.info("Tweet: %s", tweet[:120].replace("\n", " "))
            try:
                signal = oracle.analyze(tweet)
            except OracleError:
                log.exception("Oracle failed on tweet")
                continue
            log.info("Signal: %s", signal.model_dump())
            try:
                execute_trade(signal, settings, tweet=tweet)
            except TradingError:
                log.exception("Trading failed for signal")
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
