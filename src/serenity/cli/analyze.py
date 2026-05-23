"""Interactive REPL for the Oracle, with an optional Alpaca execute step."""

import logging

from rich import print as rprint
from rich.panel import Panel

from serenity.config import load_settings
from serenity.logging_config import setup_logging
from serenity.oracle import Oracle
from serenity.trading import TradeOutcome, TradingError, execute_trade
from serenity.ui import gum

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

        if signal.order_type == "N/A":
            continue

        mode = "paper" if settings.alpaca_paper else "LIVE"
        prompt = (
            f"Execute on Alpaca ({mode})? "
            f"{signal.order_type} {signal.ticker} "
            f"@ sentiment {signal.sentiment:.2f}"
        )
        try:
            should_trade = gum.confirm(prompt)
        except KeyboardInterrupt:
            continue

        if not should_trade:
            rprint("[dim]Skipped.[/]")
            continue

        try:
            outcome = execute_trade(signal, settings, tweet=text)
        except TradingError as e:
            rprint(f"[red]Trading failed:[/] {e}")
            continue

        color = "green" if outcome == TradeOutcome.EXECUTED else "yellow"
        rprint(f"[{color}]{outcome.value}[/]")


if __name__ == "__main__":
    main()
