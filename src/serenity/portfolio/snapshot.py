"""Fetch the user's current Alpaca positions as a normalised snapshot."""

from typing import Literal

from alpaca.trading.client import TradingClient
from pydantic import BaseModel, Field

PositionSide = Literal["long", "short"]


class PortfolioPosition(BaseModel):
    """One row of the user's current Alpaca book."""

    ticker: str
    side: PositionSide
    qty: float = Field(description="Signed share count. Negative for shorts.")
    avg_entry_price: float
    current_price: float
    market_value: float = Field(description="Signed. Negative for shorts.")
    unrealized_pl: float
    unrealized_plpc: float = Field(description="Fraction, e.g. 0.10 = +10%.")
    portfolio_fraction: float = Field(
        ge=0.0,
        le=1.0,
        description="|market_value| / total |market_value| across the book.",
    )


def fetch_portfolio(client: TradingClient) -> list[PortfolioPosition]:
    """Return the open positions on the account.

    Empty list when the account is flat. Each row carries a
    pre-computed `portfolio_fraction` so consumers can reason about
    concentration without a follow-up pass.
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
        side = p.side.value if hasattr(p.side, "value") else str(p.side)
        rows.append(
            PortfolioPosition(
                ticker=p.symbol,
                side=side,
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
