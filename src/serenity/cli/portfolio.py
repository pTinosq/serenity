"""Interactive portfolio review command.

Fetches the current Alpaca book, runs the portfolio reviewer LLM,
shows proposed HOLD/TRIM/CLOSE actions in a table, and asks the user
to confirm before executing.

Read-only by default. No orders are submitted until the user explicitly
confirms via gum.
"""

from __future__ import annotations

import logging

from rich import print as rprint
from rich.panel import Panel
from rich.table import Table

from serenity.config import load_settings
from serenity.logging_config import setup_logging
from serenity.portfolio import (
    PortfolioReviewError,
    PortfolioReviewer,
    fetch_portfolio,
)
from serenity.portfolio.executor import execute_review
from serenity.trading import get_client
from serenity.ui import gum

log = logging.getLogger(__name__)

ACTION_COLOR = {"HOLD": "dim", "TRIM": "yellow", "CLOSE": "red"}


def render_positions(positions) -> Table:
    table = Table(title="Current portfolio", show_lines=False)
    table.add_column("Ticker")
    table.add_column("Side")
    table.add_column("Qty", justify="right")
    table.add_column("Entry $", justify="right")
    table.add_column("Last $", justify="right")
    table.add_column("Mkt val $", justify="right")
    table.add_column("Unreal P&L", justify="right")
    table.add_column("% of book", justify="right")

    for p in positions:
        pl_color = "green" if p.unrealized_pl >= 0 else "red"
        table.add_row(
            p.ticker,
            p.side,
            f"{p.qty:.4f}".rstrip("0").rstrip("."),
            f"{p.avg_entry_price:.2f}",
            f"{p.current_price:.2f}",
            f"{p.market_value:.2f}",
            f"[{pl_color}]{p.unrealized_pl:+.2f} ({p.unrealized_plpc * 100:+.1f}%)[/]",
            f"{p.portfolio_fraction * 100:.1f}%",
        )
    return table


def render_actions(review) -> Table:
    table = Table(title="Reviewer recommendations", show_lines=True)
    table.add_column("Ticker")
    table.add_column("Action")
    table.add_column("Trim %", justify="right")
    table.add_column("Reasoning")

    for action in review.actions:
        color = ACTION_COLOR.get(action.action, "white")
        trim_cell = f"{action.trim_fraction * 100:.0f}%" if action.action == "TRIM" else "—"
        table.add_row(
            action.ticker,
            f"[{color}]{action.action}[/]",
            trim_cell,
            action.reasoning,
        )
    return table


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        rprint("[red]Alpaca credentials not configured.[/] Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env.")
        return

    client = get_client()

    rprint("[dim]Fetching positions from Alpaca…[/]")
    positions = fetch_portfolio(client)
    if not positions:
        rprint("[yellow]Account has no open positions. Nothing to review.[/]")
        return

    rprint(render_positions(positions))

    rprint("[dim]Asking the reviewer…[/]")
    try:
        review = PortfolioReviewer(settings=settings).review(positions)
    except PortfolioReviewError as e:
        rprint(f"[red]Review failed:[/] {e}")
        return

    rprint(Panel.fit(review.summary, title="Summary", border_style="cyan"))
    rprint(render_actions(review))

    non_hold = [a for a in review.actions if a.action != "HOLD"]
    if not non_hold:
        rprint("[green]Everything is HOLD. No orders to submit.[/]")
        return

    mode = "paper" if settings.alpaca_paper else "LIVE"
    prompt = f"Execute {len(non_hold)} non-HOLD actions on Alpaca ({mode})?"
    try:
        should_execute = gum.confirm(prompt)
    except KeyboardInterrupt:
        rprint("[dim]Cancelled.[/]")
        return

    if not should_execute:
        rprint("[dim]Skipped — no orders submitted.[/]")
        return

    results = execute_review(client, review)
    for line in results:
        rprint(f"  • {line}")


if __name__ == "__main__":
    main()
