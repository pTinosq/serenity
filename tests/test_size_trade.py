"""Tests for the trade-sizing function.

Pure function — no Alpaca, no LLM. Lives in tests/ to anchor the
pattern; add similar unit tests for the other guards as you go.
"""

from __future__ import annotations

import pytest

from serenity.config import Settings
from serenity.oracle.models import TradeSignal
from serenity.trading import size_trade


def make_signal(sentiment: float, order_type: str = "BUY") -> TradeSignal:
    return TradeSignal(
        ticker="AAPL",
        order_type=order_type,  # type: ignore[arg-type]
        confidence=0.9,
        sentiment=sentiment,
    )


def test_full_sentiment_uses_max_trade(settings: Settings) -> None:
    notional = size_trade(make_signal(1.0), available_cash=10_000.0, settings=settings)
    assert notional == pytest.approx(settings.max_trade_usd)


def test_mid_sentiment_scales_linearly(settings: Settings) -> None:
    notional = size_trade(make_signal(0.5), available_cash=10_000.0, settings=settings)
    assert notional == pytest.approx(0.5 * settings.max_trade_usd)


def test_zero_sentiment_returns_zero(settings: Settings) -> None:
    # Caller is responsible for the BELOW_MIN_TRADE skip; size_trade
    # itself doesn't enforce the floor.
    notional = size_trade(make_signal(0.0), available_cash=10_000.0, settings=settings)
    assert notional == 0.0


def test_cash_clamp_kicks_in_when_sized_value_exceeds_cash(settings: Settings) -> None:
    notional = size_trade(make_signal(1.0), available_cash=15.0, settings=settings)
    assert notional == pytest.approx(15.0)


def test_max_trade_clamp_never_exceeded_even_with_large_cash(settings: Settings) -> None:
    notional = size_trade(make_signal(1.0), available_cash=1_000_000.0, settings=settings)
    assert notional == pytest.approx(settings.max_trade_usd)
