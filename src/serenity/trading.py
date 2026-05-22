"""Execute TradeSignals via Alpaca.

Bare-bones: turn a TradeSignal into a market order, sized by
MAX_ORDER_AMOUNT_USD as notional. Skips no-signal cases and anything
below MIN_CONFIDENCE. Paper trading is the default.
"""

from __future__ import annotations

import logging
from enum import Enum
from functools import lru_cache

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from serenity.config import Settings, load_settings
from serenity.oracle.models import TradeSignal

log = logging.getLogger(__name__)


class TradeOutcome(str, Enum):
    EXECUTED = "executed"
    SKIPPED_NO_SIGNAL = "skipped:no_signal"
    SKIPPED_LOW_CONFIDENCE = "skipped:low_confidence"
    FAILED = "failed"


class TradingError(RuntimeError):
    """Raised when an order submission fails."""


@lru_cache(maxsize=1)
def get_client() -> TradingClient:
    settings = load_settings()
    return TradingClient(
        api_key=settings.alpaca_api_key.get_secret_value(),
        secret_key=settings.alpaca_secret_key.get_secret_value(),
        paper=settings.alpaca_paper,
    )


def execute_trade(signal: TradeSignal, settings: Settings) -> TradeOutcome:
    """Submit a market order for `signal`, or skip with a reason."""
    if signal.order_type == "N/A":
        log.info("Skipping: no actionable signal")
        return TradeOutcome.SKIPPED_NO_SIGNAL

    if signal.confidence < settings.min_confidence:
        log.info(
            "Skipping %s: confidence %.2f < %.2f",
            signal.ticker,
            signal.confidence,
            settings.min_confidence,
        )
        return TradeOutcome.SKIPPED_LOW_CONFIDENCE

    side = OrderSide.BUY if signal.order_type == "BUY" else OrderSide.SELL
    notional = settings.max_order_amount_usd

    request = MarketOrderRequest(
        symbol=signal.ticker,
        notional=notional,
        side=side,
        time_in_force=TimeInForce.DAY,
    )

    try:
        order = get_client().submit_order(order_data=request)
    except APIError as e:
        raise TradingError(f"Alpaca rejected {side.value} {signal.ticker}: {e}") from e

    log.info(
        "Order %s: %s $%.2f %s — status=%s",
        order.id,
        side.value,
        notional,
        signal.ticker,
        order.status,
    )
    return TradeOutcome.EXECUTED
