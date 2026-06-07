"""Portfolio review agent.

Pulls the current Alpaca positions and asks an LLM to recommend
HOLD / TRIM / CLOSE actions for each. The output is advisory — the
human reviews suggestions and confirms before any orders go in.

This is a counterweight to the tweet-driven entry path. The Oracle
opens positions one tweet at a time without any awareness of what
the account already holds; the portfolio reviewer reads the entire
book and reasons about concentration, profit-taking, and loss-cutting
across the whole snapshot.
"""

from serenity.portfolio.models import PortfolioPosition, PortfolioReview, PositionAction
from serenity.portfolio.agent import PortfolioReviewer, PortfolioReviewError
from serenity.portfolio.snapshot import fetch_portfolio

__all__ = [
    "PortfolioPosition",
    "PortfolioReview",
    "PositionAction",
    "PortfolioReviewer",
    "PortfolioReviewError",
    "fetch_portfolio",
]
