"""Execute the actions in a PortfolioReview via Alpaca."""

from __future__ import annotations

import logging

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import ClosePositionRequest

from serenity.portfolio.models import PortfolioReview, PositionAction

log = logging.getLogger(__name__)


def execute_action(client: TradingClient, action: PositionAction) -> str:
    """Submit the trade implied by `action`. Returns a human-readable result line.

    Uses Alpaca's close_position endpoint for TRIM and CLOSE (Alpaca handles
    short positions and fractional shares internally — submitting `qty` or
    `percentage` here is symmetric across long/short, unlike a raw market
    order which would have to invert the side for a short close).
    """
    if action.action == "HOLD":
        return f"{action.ticker}: held"

    if action.action == "CLOSE":
        try:
            order = client.close_position(action.ticker)
        except APIError as e:
            raise RuntimeError(f"Close {action.ticker} failed: {e}") from e
        return f"{action.ticker}: close submitted (order {order.id}, status {order.status})"

    if action.action == "TRIM":
        if not (0 < action.trim_fraction < 1):
            raise ValueError(
                f"TRIM {action.ticker}: trim_fraction must be in (0, 1), got {action.trim_fraction}"
            )
        percentage = f"{action.trim_fraction * 100:.0f}"
        try:
            order = client.close_position(
                action.ticker,
                close_options=ClosePositionRequest(percentage=percentage),
            )
        except APIError as e:
            raise RuntimeError(f"Trim {action.ticker} failed: {e}") from e
        return (
            f"{action.ticker}: trim {percentage}% submitted "
            f"(order {order.id}, status {order.status})"
        )

    raise ValueError(f"Unknown action {action.action!r} on {action.ticker}")


def execute_review(client: TradingClient, review: PortfolioReview) -> list[str]:
    """Execute every non-HOLD action in `review`, returning per-action result lines.

    Each action is submitted independently. A failure on one ticker is logged
    and recorded in the output but does not stop later actions — partial
    application is preferable to silently dropping later trades.
    """
    results: list[str] = []
    for action in review.actions:
        try:
            results.append(execute_action(client, action))
        except Exception as e:
            log.exception("Action %s on %s failed", action.action, action.ticker)
            results.append(f"{action.ticker}: FAILED ({e})")
    return results
