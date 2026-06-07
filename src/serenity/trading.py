"""Low-level Alpaca primitives shared across the bot.

Used to be the home of `execute_trade` — a monolithic per-tweet executor.
That logic now lives in the agent harness (`serenity.executor`): the
Oracle produces a signal, the TradeExecutor agent decides actions, and
`apply_plan` submits them with hard risk guards.

This module keeps only the things that genuinely belong at the
infrastructure layer: cached Alpaca client builders, and the
sentiment-to-notional sizing utility.
"""

from functools import lru_cache

from alpaca.trading.client import TradingClient

from serenity.config import Settings, load_settings
from serenity.oracle.models import TradeSignal


@lru_cache(maxsize=1)
def get_client() -> TradingClient:
    settings = load_settings()
    return TradingClient(
        api_key=settings.alpaca_api_key.get_secret_value(),
        secret_key=settings.alpaca_secret_key.get_secret_value(),
        paper=settings.alpaca_paper,
    )


def size_trade(signal: TradeSignal, available_cash: float, settings: Settings) -> float:
    """Sentiment-weighted notional, clamped to MAX_TRADE_USD and cash.

    The main per-tweet pipeline now lets the TradeExecutor agent decide
    sizing (factoring in portfolio context the Oracle can't see). This
    helper remains as the canonical encoding of "default" sizing for
    callers that want it (e.g. CLI smoke tools, future agents that ask
    the LLM to suggest a notional and want a fallback).

    Callers check the result against `MIN_TRADE_USD`; trades sized below
    the floor should be skipped rather than rounded up.
    """
    target = signal.sentiment * settings.max_trade_usd
    return min(target, settings.max_trade_usd, available_cash)
