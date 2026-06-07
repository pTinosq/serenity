"""Interactive REPL for the Oracle, with an optional execute step.

Type a tweet, see the Oracle's signal. If a signal is actionable and
Alpaca credentials are configured, optionally let the TradeExecutor
plan + submit. Useful for prompt-testing the Oracle and end-to-end
exercising the new executor path without waiting for a real tweet.
"""

import logging

from rich import print as rprint
from rich.panel import Panel

from serenity.config import load_settings
from serenity.executor import TradeExecutor, apply_plan
from serenity.logging_config import setup_logging
from serenity.oracle import Oracle
from serenity.portfolio import fetch_portfolio
from serenity.trading import get_client
from serenity.ui import gum

log = logging.getLogger(__name__)


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

    oracle = Oracle(settings=settings)
    executor = TradeExecutor(settings=settings)

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
        if not settings.alpaca_api_key or not settings.alpaca_secret_key:
            rprint("[dim]Alpaca not configured — Oracle output only.[/]")
            continue

        client = get_client()
        try:
            cash = float(client.get_account().cash)
            positions = fetch_portfolio(client)
        except Exception:
            log.exception("Failed to fetch account state")
            continue

        try:
            plan = executor.decide(
                tweet=text, signal=signal, positions=positions, available_cash=cash,
            )
        except Exception:
            log.exception("Executor failed")
            continue

        rprint(
            Panel.fit(
                plan.model_dump_json(indent=2),
                title="TradePlan",
                border_style="yellow",
            )
        )

        if not plan.actions or all(a.action == "HOLD" for a in plan.actions):
            rprint("[dim]Empty / HOLD-only plan. Nothing to submit.[/]")
            continue

        mode = "paper" if settings.alpaca_paper else "LIVE"
        try:
            should_trade = gum.confirm(f"Execute {len(plan.actions)} action(s) on Alpaca ({mode})?")
        except KeyboardInterrupt:
            continue
        if not should_trade:
            rprint("[dim]Skipped.[/]")
            continue

        outcomes = apply_plan(client, settings, plan, available_cash=cash)
        for o in outcomes:
            rprint(f"  • {o.action.action} {o.action.ticker} → [{o.outcome.value}] {o.detail}")


if __name__ == "__main__":
    main()
