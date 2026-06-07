"""Fetch the user's current Alpaca positions as a normalised snapshot."""

from __future__ import annotations

from alpaca.trading.client import TradingClient

from serenity.portfolio.models import PortfolioPosition


def fetch_portfolio(client: TradingClient) -> list[PortfolioPosition]:
    """Return the open positions on the account as a list of PortfolioPosition.

    Empty list when the account is flat. Computes each row's
    portfolio_fraction so the reviewer can reason about concentration
    without a follow-up pass over the data.
    """
    positions = client.get_all_positions()
    if not positions:
        return []

    total_abs_value = sum(abs(float(p.market_value or 0)) for p in positions)
    if total_abs_value == 0:
        return []

    rows: list[PortfolioPosition] = []
    for p in positions:
        market_value = float(p.market_value or 0)
        rows.append(
            PortfolioPosition(
                ticker=p.symbol,
                side=p.side.value if hasattr(p.side, "value") else str(p.side),
                qty=float(p.qty),
                avg_entry_price=float(p.avg_entry_price),
                current_price=float(p.current_price or 0),
                market_value=market_value,
                unrealized_pl=float(p.unrealized_pl or 0),
                unrealized_plpc=float(p.unrealized_plpc or 0),
                portfolio_fraction=abs(market_value) / total_abs_value,
            )
        )
    return rows
