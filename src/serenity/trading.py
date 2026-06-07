"""Execute TradeSignals via Alpaca.

Position size scales with the signal's sentiment magnitude:
    notional = clamp(sentiment * MAX_TRADE_USD, MIN_TRADE_USD, MAX_TRADE_USD)
and is further clamped to the account's available cash. Skips
no-signal cases, anything below MIN_CONFIDENCE, and orders that would
fall below MIN_TRADE_USD.

Alpaca rejects fractional shorts — submitting a SELL on a ticker you
don't hold must use whole shares. We detect that rejection and retry
with `qty = floor(notional / price)`, skipping if even one share
costs more than the sized notional.

Paper trading is the default.
"""

from __future__ import annotations

import logging
from enum import Enum
from functools import lru_cache

from alpaca.common.exceptions import APIError
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from serenity.alerts import Alert, Messenger
from serenity.config import Settings, load_settings
from serenity.oracle.models import TradeSignal

log = logging.getLogger(__name__)


class TradeOutcome(str, Enum):
    EXECUTED = "executed"
    SKIPPED_NO_SIGNAL = "skipped:no_signal"
    SKIPPED_LOW_CONFIDENCE = "skipped:low_confidence"
    SKIPPED_BELOW_MIN_TRADE = "skipped:below_min_trade"
    SKIPPED_PRICE_TOO_HIGH = "skipped:price_too_high"
    SKIPPED_NOT_TRADEABLE = "skipped:not_tradeable"
    SKIPPED_NO_CASH = "skipped:no_cash"
    SKIPPED_NO_CREDENTIALS = "skipped:no_credentials"
    SKIPPED_POSITION_CAP = "skipped:position_cap"
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


@lru_cache(maxsize=1)
def get_data_client() -> StockHistoricalDataClient:
    settings = load_settings()
    return StockHistoricalDataClient(
        api_key=settings.alpaca_api_key.get_secret_value(),
        secret_key=settings.alpaca_secret_key.get_secret_value(),
    )


def get_latest_price(symbol: str) -> float:
    """Last trade price — always populated even outside market hours."""
    req = StockLatestTradeRequest(symbol_or_symbols=symbol)
    return float(get_data_client().get_stock_latest_trade(req)[symbol].price)


def size_trade(signal: TradeSignal, available_cash: float, settings: Settings) -> float:
    """Return the notional USD to deploy for this signal, before any skip checks.

    Caller checks the result against `MIN_TRADE_USD`; trades sized below the
    floor are skipped rather than rounded up.
    """
    target = signal.sentiment * settings.max_trade_usd
    return min(target, settings.max_trade_usd, available_cash)


def current_position_value(client: TradingClient, symbol: str) -> float:
    """USD market value of the current position in `symbol`, signed.

    Long positions are positive, shorts are negative. Returns 0 if no
    position is open. Alpaca returns 404 when no position exists; treat
    that as the empty case.
    """
    try:
        position = client.get_open_position(symbol)
    except APIError as e:
        if e.status_code in (404, 422):
            return 0.0
        raise
    if position.market_value is None:
        return 0.0
    return float(position.market_value)


def is_fractional_short_rejection(e: APIError, side: OrderSide) -> bool:
    return (
        side == OrderSide.SELL
        and e.status_code == 422
        and "fractional" in str(e).lower()
    )


def is_asset_not_tradeable(e: APIError) -> bool:
    """Alpaca rejects unknown / inactive / non-US tickers with code 40010001."""
    msg = str(e).lower()
    return e.status_code == 422 and ("not active" in msg or "not found" in msg)


def alpaca_401_message(settings: Settings, side: OrderSide, ticker: str) -> str:
    mode = "paper" if settings.alpaca_paper else "live"
    return (
        f"Alpaca rejected {side.value} {ticker}: 401 unauthorized. "
        f"ALPACA_PAPER is {settings.alpaca_paper} ({mode} endpoint) — "
        f"make sure your ALPACA_API_KEY/ALPACA_SECRET_KEY are {mode} keys. "
        "Paper and live keys are not interchangeable."
    )


def submit_short_whole_share(
    client: TradingClient,
    signal: TradeSignal,
    notional: float,
    tweet: str | None = None,
) -> TradeOutcome:
    """Open a short with whole-share qty, sized from the latest trade price."""
    try:
        price = get_latest_price(signal.ticker)
    except APIError as e:
        raise TradingError(
            f"Couldn't fetch price for {signal.ticker} to size short: {e}"
        ) from e
    qty = int(notional // price)
    if qty < 1:
        log.info(
            "Skipping short %s: price $%.2f > sized notional $%.2f",
            signal.ticker,
            price,
            notional,
        )
        return TradeOutcome.SKIPPED_PRICE_TOO_HIGH

    request = MarketOrderRequest(
        symbol=signal.ticker,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    )
    try:
        order = client.submit_order(order_data=request)
    except APIError as e:
        raise TradingError(
            f"Alpaca rejected short {qty} {signal.ticker}: {e}"
        ) from e

    log.info(
        "Order %s: SHORT %d %s @ ~$%.2f (≈$%.2f, sentiment=%.2f) — status=%s",
        order.id,
        qty,
        signal.ticker,
        price,
        qty * price,
        signal.sentiment,
        order.status,
    )
    Messenger.send(Alert(
        reason="trade_executed",
        title=f"Shorted {qty} {signal.ticker} @ ~${price:.2f} (≈${qty * price:.2f})",
        signal=signal,
        amount=qty * price,
        tweet=tweet,
    ))
    return TradeOutcome.EXECUTED


def execute_trade(
    signal: TradeSignal,
    settings: Settings,
    tweet: str | None = None,
) -> TradeOutcome:
    """Submit a market order for `signal`, or skip with a reason.

    `tweet` is the source text the signal came from; when supplied it's
    attached to any fallback alert so the user has the original context.
    """
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

    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        log.warning(
            "Skipping %s: Alpaca credentials not configured "
            "(set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env)",
            signal.ticker,
        )
        return TradeOutcome.SKIPPED_NO_CREDENTIALS

    client = get_client()
    cash = float(client.get_account().cash)

    if cash < settings.min_trade_usd:
        log.warning(
            "Skipping %s: cash $%.2f < MIN_TRADE_USD $%.2f",
            signal.ticker,
            cash,
            settings.min_trade_usd,
        )
        return TradeOutcome.SKIPPED_NO_CASH

    notional = size_trade(signal, cash, settings)
    if notional < settings.min_trade_usd:
        log.info(
            "Skipping %s: sized to $%.2f, below MIN_TRADE_USD $%.2f "
            "(sentiment=%.2f, cash=$%.2f)",
            signal.ticker,
            notional,
            settings.min_trade_usd,
            signal.sentiment,
            cash,
        )
        return TradeOutcome.SKIPPED_BELOW_MIN_TRADE

    side = OrderSide.BUY if signal.order_type == "BUY" else OrderSide.SELL

    if side == OrderSide.BUY and settings.max_position_usd > 0:
        position_value = abs(current_position_value(client, signal.ticker))
        headroom = settings.max_position_usd - position_value
        if headroom < settings.min_trade_usd:
            log.info(
                "Skipping BUY %s: position $%.2f >= cap $%.2f (headroom $%.2f < MIN $%.2f)",
                signal.ticker,
                position_value,
                settings.max_position_usd,
                headroom,
                settings.min_trade_usd,
            )
            Messenger.send(Alert(
                reason="position_cap",
                title=f"BUY {signal.ticker} skipped (position cap ${settings.max_position_usd:.0f} reached)",
                signal=signal,
                amount=notional,
                tweet=tweet,
                detail=(
                    f"Current {signal.ticker} position is ${position_value:.2f}, at or above "
                    f"MAX_POSITION_USD (${settings.max_position_usd:.2f}). The signal was "
                    "skipped to keep concentration in a single name capped. Raise "
                    "MAX_POSITION_USD or trim the position manually if you want more exposure."
                ),
            ))
            return TradeOutcome.SKIPPED_POSITION_CAP
        if notional > headroom:
            log.info(
                "Sizing down BUY %s: $%.2f -> $%.2f to respect MAX_POSITION_USD ($%.2f)",
                signal.ticker,
                notional,
                headroom,
                settings.max_position_usd,
            )
            notional = headroom

    request = MarketOrderRequest(
        symbol=signal.ticker,
        notional=round(notional, 2),
        side=side,
        time_in_force=TimeInForce.DAY,
    )

    try:
        order = client.submit_order(order_data=request)
    except APIError as e:
        if e.status_code == 401:
            raise TradingError(alpaca_401_message(settings, side, signal.ticker)) from e
        if is_asset_not_tradeable(e):
            log.warning(
                "Skipping %s: not tradeable on Alpaca (likely a foreign listing "
                "or delisted ticker the Oracle misidentified as US-listed)",
                signal.ticker,
            )
            Messenger.send(Alert(
                reason="not_tradeable",
                title=f"{signal.ticker} not tradeable on Alpaca",
                signal=signal,
                amount=notional,
                tweet=tweet,
                detail=(
                    "Alpaca rejected this ticker as inactive. Most often it's "
                    "a foreign listing (e.g. Nasdaq Stockholm) the Oracle "
                    "couldn't tell apart from a US cashtag. Trade manually on "
                    "your own broker if you want exposure."
                ),
            ))
            return TradeOutcome.SKIPPED_NOT_TRADEABLE
        if is_fractional_short_rejection(e, side):
            log.info("Retrying %s SELL as whole-share short", signal.ticker)
            return submit_short_whole_share(client, signal, notional, tweet=tweet)
        raise TradingError(f"Alpaca rejected {side.value} {signal.ticker}: {e}") from e

    log.info(
        "Order %s: %s $%.2f %s (sentiment=%.2f, cash=$%.2f) — status=%s",
        order.id,
        side.value,
        notional,
        signal.ticker,
        signal.sentiment,
        cash,
        order.status,
    )
    Messenger.send(Alert(
        reason="trade_executed",
        title=f"{side.value} ${notional:.2f} {signal.ticker}",
        signal=signal,
        amount=notional,
        tweet=tweet,
    ))
    return TradeOutcome.EXECUTED
