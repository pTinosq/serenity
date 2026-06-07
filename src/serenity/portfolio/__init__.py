"""Portfolio snapshot — the bot's view of what Alpaca says it holds.

Single-file module: one model, one function. The trade executor reads
this snapshot as part of its decision context.
"""

from serenity.portfolio.snapshot import PortfolioPosition, fetch_portfolio

__all__ = ["PortfolioPosition", "fetch_portfolio"]
