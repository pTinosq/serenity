"""Interactive REPL for the Oracle."""

import logging

from rich import print as rprint
from rich.panel import Panel

from serenity.config import load_settings
from serenity.logging_config import setup_logging
from serenity.oracle import Oracle

log = logging.getLogger(__name__)


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

    oracle = Oracle(settings=settings)

    rprint(
        Panel.fit(
            "[bold cyan]Oracle REPL[/]\nType a tweet; press Ctrl-D to exit.",
            border_style="cyan",
        )
    )

    while True:
        try:
            text = input("\n> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not text.strip():
            continue

        try:
            signal = oracle.analyze(text)
        except Exception:
            log.exception("Oracle call failed")
            continue

        rprint(
            Panel.fit(
                signal.model_dump_json(indent=2),
                title="TradeSignal",
                border_style="green",
            )
        )


if __name__ == "__main__":
    main()
