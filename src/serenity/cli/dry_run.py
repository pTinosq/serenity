"""Offline pipeline tester: fake tweet + fake portfolio → see what the bot would do.

Runs the same Oracle → TradeExecutor flow the live bot uses, but with
a hand-edited portfolio snapshot from a JSON file instead of a live
Alpaca account. No orders are submitted — the script prints the
TradePlan the executor produced and stops there.

Use it to:
- Sanity-check the executor's prompt by feeding it crafted tweets
- Reproduce a specific real-world scenario ("what if I already hold
  $1k of XFAB and a strong BUY tweet lands?") without burning your
  paper account
- Iterate on the prompt without ever needing Alpaca credentials

Usage:

    just dry-run "Your fake tweet text here"
    just dry-run --state dry_run_state.example.json "Tweet"

The state file is JSON with `cash: float` and `positions: list`.
Each position needs: ticker, side ("long" | "short"), qty,
avg_entry_price, current_price, market_value, unrealized_pl,
unrealized_plpc. See `dry_run_state.example.json` for the shape.
`portfolio_fraction` is computed automatically from market_values.

A missing state file is treated as "empty account, $1000 cash" so a
quick smoke test works with zero setup.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from rich import print as rprint
from rich.panel import Panel

from serenity.config import load_settings
from serenity.executor import TradeExecutor
from serenity.logging_config import setup_logging
from serenity.oracle import Oracle
from serenity.portfolio.snapshot import PortfolioPosition

DEFAULT_STATE_PATH = Path("dry_run_state.json")

EMPTY_STATE = {"cash": 1000.0, "positions": []}


def load_state(path: Path) -> dict:
    if not path.exists():
        return dict(EMPTY_STATE)
    return json.loads(path.read_text(encoding="utf-8"))


def build_positions(raw_positions: list[dict]) -> list[PortfolioPosition]:
    """Turn the JSON shape into PortfolioPosition, computing portfolio_fraction."""
    if not raw_positions:
        return []
    total_abs = sum(abs(float(p.get("market_value", 0))) for p in raw_positions) or 1.0
    return [
        PortfolioPosition(
            ticker=p["ticker"],
            side=p["side"],
            qty=float(p["qty"]),
            avg_entry_price=float(p["avg_entry_price"]),
            current_price=float(p["current_price"]),
            market_value=float(p["market_value"]),
            unrealized_pl=float(p["unrealized_pl"]),
            unrealized_plpc=float(p["unrealized_plpc"]),
            portfolio_fraction=abs(float(p["market_value"])) / total_abs,
        )
        for p in raw_positions
    ]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="serenity-dry-run",
        description="Run a tweet through the live Oracle + TradeExecutor with a fake portfolio.",
    )
    parser.add_argument(
        "tweet",
        nargs="?",
        help=(
            "The tweet text to feed the pipeline. If omitted, the script "
            "reads stdin so you can `echo \"...\" | just dry-run`."
        ),
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=DEFAULT_STATE_PATH,
        help=(
            f"Path to the portfolio state JSON. Default: {DEFAULT_STATE_PATH}. "
            "Missing file = empty account with $1000 cash."
        ),
    )
    parser.add_argument(
        "--cash",
        type=float,
        help="Override the `cash` from the state file. Useful for quick A/B sizing tests.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    settings = load_settings()
    setup_logging(settings.log_level)

    tweet = args.tweet or sys.stdin.read().strip()
    if not tweet:
        rprint("[red]No tweet provided.[/] Pass as an argument or pipe via stdin.")
        sys.exit(2)

    state = load_state(args.state)
    cash = float(args.cash if args.cash is not None else state.get("cash", 0.0))
    positions = build_positions(state.get("positions", []))

    rprint(
        Panel.fit(
            f"[bold]Tweet[/]\n{tweet}\n\n"
            f"[bold]Cash[/]: ${cash:.2f}\n"
            f"[bold]Positions[/]: {len(positions)}",
            border_style="cyan",
        )
    )

    oracle = Oracle(settings=settings)
    try:
        signal = oracle.analyze(tweet)
    except Exception as e:
        rprint(f"[red]Oracle failed:[/] {e}")
        sys.exit(1)
    rprint(Panel.fit(signal.model_dump_json(indent=2), title="TradeSignal", border_style="green"))

    if signal.order_type == "N/A":
        rprint("[dim]Signal is N/A — executor not called.[/]")
        return
    if signal.confidence < settings.min_confidence:
        rprint(
            f"[dim]Signal confidence {signal.confidence:.2f} below MIN_CONFIDENCE "
            f"{settings.min_confidence:.2f} — executor not called.[/]"
        )
        return

    executor = TradeExecutor(settings=settings)
    try:
        plan = executor.decide(
            tweet=tweet,
            signal=signal,
            positions=positions,
            available_cash=cash,
        )
    except Exception as e:
        rprint(f"[red]Executor failed:[/] {e}")
        sys.exit(1)

    rprint(Panel.fit(plan.model_dump_json(indent=2), title="TradePlan", border_style="yellow"))
    rprint("[dim]Dry run — no orders were submitted.[/]")


if __name__ == "__main__":
    main()
