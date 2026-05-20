import argparse
import logging

from serenity.config import load_settings
from serenity.logging_config import setup_logging
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
    """Run the bot loop. Placeholder until the Twitter and Trading stages land."""
    log.info("Starting [bold cyan]serenity[/] :sparkles:")
    log.debug("Loaded settings: %s", load_settings().model_dump())


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
