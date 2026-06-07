"""Apply a TradePlan to Alpaca with hard safety guards.

The TradeExecutor agent is supposed to respect the risk bounds in its
prompt, but a misbehaving LLM cannot be the only thing standing between
real money and a bad day. This module enforces the guards as hard
checks at submission time:

- BUY notional must be in [MIN_TRADE_USD, MAX_TRADE_USD]
- BUY notional <= available cash
- BUY post-trade exposure in the ticker <= MAX_POSITION_USD (sized down
  to fit headroom if needed)
- TRIM / CLOSE require an existing position; missing positions are
  skipped
- Daily order cap (counts orders Alpaca has seen on this account since
  UTC midnight). Once hit, the entire plan is skipped.

Each action returns an ActionOutcome describing whether and how it was
applied. The caller (main loop, CLI) decides what to do with the
outcomes — log, alert, render, etc.
"""

import logging
from datetime import datetime, time, timezone
from enum import Enum

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import (
    ClosePositionRequest,
    GetOrdersRequest,
    MarketOrderRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce
from pydantic import BaseModel

from serenity.config import Settings
from serenity.executor.models import TradeAction, TradePlan

log = logging.getLogger(__name__)


class Outcome(str, Enum):
    EXECUTED = "executed"
    HELD = "held"
    SKIPPED_NO_POSITION = "skipped:no_position"
    SKIPPED_BELOW_MIN_TRADE = "skipped:below_min_trade"
    SKIPPED_NO_CASH = "skipped:no_cash"
    SKIPPED_POSITION_CAP = "skipped:position_cap"
    SKIPPED_DAILY_CAP = "skipped:daily_cap"
    SKIPPED_INVALID = "skipped:invalid_action"
    FAILED = "failed"


class ActionOutcome(BaseModel):
    action: TradeAction
    outcome: Outcome
    detail: str = ""
    submitted_notional: float | None = None
    order_id: str | None = None


def _orders_today(client: TradingClient) -> int:
    midnight = datetime.combine(
        datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc
    )
    request = GetOrdersRequest(status=QueryOrderStatus.ALL, after=midnight, limit=500)
    return len(client.get_orders(filter=request))


def _position_market_value(client: TradingClient, ticker: str) -> float:
    """Signed market value of the current position in `ticker`, or 0.0 if none."""
    try:
        position = client.get_open_position(ticker)
    except APIError as e:
        if e.status_code in (404, 422):
            return 0.0
        raise
    return float(position.market_value or 0)


def _apply_buy(
    client: TradingClient,
    settings: Settings,
    action: TradeAction,
    cash: float,
) -> ActionOutcome:
    notional = action.notional_usd or 0.0

    position_value = abs(_position_market_value(client, action.ticker))
    headroom = settings.max_position_usd - position_value
    if settings.max_position_usd > 0 and headroom < settings.min_trade_usd:
        return ActionOutcome(
            action=action,
            outcome=Outcome.SKIPPED_POSITION_CAP,
            detail=(
                f"position ${position_value:.2f} >= cap ${settings.max_position_usd:.2f} "
                f"(headroom ${headroom:.2f} < min ${settings.min_trade_usd:.2f})"
            ),
        )
    if settings.max_position_usd > 0 and notional > headroom:
        log.info(
            "Sizing down BUY %s: $%.2f -> $%.2f to respect MAX_POSITION_USD",
            action.ticker, notional, headroom,
        )
        notional = headroom

    if notional > cash:
        notional = cash
    if notional < settings.min_trade_usd:
        return ActionOutcome(
            action=action,
            outcome=Outcome.SKIPPED_BELOW_MIN_TRADE,
            detail=f"sized to ${notional:.2f}, below MIN_TRADE_USD ${settings.min_trade_usd:.2f}",
        )
    if cash < settings.min_trade_usd:
        return ActionOutcome(
            action=action,
            outcome=Outcome.SKIPPED_NO_CASH,
            detail=f"cash ${cash:.2f} < min ${settings.min_trade_usd:.2f}",
        )

    notional = min(notional, settings.max_trade_usd)

    try:
        order = client.submit_order(
            order_data=MarketOrderRequest(
                symbol=action.ticker,
                notional=round(notional, 2),
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            )
        )
    except APIError as e:
        return ActionOutcome(
            action=action,
            outcome=Outcome.FAILED,
            detail=f"Alpaca rejected BUY: {e}",
        )
    return ActionOutcome(
        action=action,
        outcome=Outcome.EXECUTED,
        detail=f"BUY ${notional:.2f}",
        submitted_notional=notional,
        order_id=str(order.id),
    )


def _apply_trim(
    client: TradingClient, action: TradeAction
) -> ActionOutcome:
    fraction = action.trim_fraction or 0.0
    if not (0.0 < fraction < 1.0):
        return ActionOutcome(
            action=action,
            outcome=Outcome.SKIPPED_INVALID,
            detail=f"trim_fraction {fraction} not in (0, 1)",
        )
    if _position_market_value(client, action.ticker) == 0.0:
        return ActionOutcome(
            action=action,
            outcome=Outcome.SKIPPED_NO_POSITION,
            detail="no existing position to trim",
        )
    percentage = f"{fraction * 100:.0f}"
    try:
        order = client.close_position(
            action.ticker, close_options=ClosePositionRequest(percentage=percentage)
        )
    except APIError as e:
        return ActionOutcome(
            action=action,
            outcome=Outcome.FAILED,
            detail=f"Alpaca rejected TRIM: {e}",
        )
    return ActionOutcome(
        action=action,
        outcome=Outcome.EXECUTED,
        detail=f"TRIM {percentage}%",
        order_id=str(order.id),
    )


def _apply_close(
    client: TradingClient, action: TradeAction
) -> ActionOutcome:
    if _position_market_value(client, action.ticker) == 0.0:
        return ActionOutcome(
            action=action,
            outcome=Outcome.SKIPPED_NO_POSITION,
            detail="no existing position to close",
        )
    try:
        order = client.close_position(action.ticker)
    except APIError as e:
        return ActionOutcome(
            action=action,
            outcome=Outcome.FAILED,
            detail=f"Alpaca rejected CLOSE: {e}",
        )
    return ActionOutcome(
        action=action,
        outcome=Outcome.EXECUTED,
        detail="CLOSE",
        order_id=str(order.id),
    )


def apply_plan(
    client: TradingClient,
    settings: Settings,
    plan: TradePlan,
    *,
    available_cash: float,
) -> list[ActionOutcome]:
    """Execute every non-HOLD action in `plan`, returning per-action outcomes.

    Hard guards run before submission. An individual action failing
    does not stop later actions — partial application beats silently
    dropping later trades.
    """
    if not plan.actions:
        return []

    if settings.max_trades_per_day > 0:
        today_count = _orders_today(client)
        if today_count >= settings.max_trades_per_day:
            return [
                ActionOutcome(
                    action=a,
                    outcome=Outcome.SKIPPED_DAILY_CAP,
                    detail=f"{today_count} orders already today >= cap {settings.max_trades_per_day}",
                )
                for a in plan.actions
            ]

    outcomes: list[ActionOutcome] = []
    remaining_cash = available_cash
    for action in plan.actions:
        if action.action == "HOLD":
            outcomes.append(ActionOutcome(action=action, outcome=Outcome.HELD))
            continue
        if action.action == "BUY":
            outcome = _apply_buy(client, settings, action, remaining_cash)
            if outcome.outcome == Outcome.EXECUTED and outcome.submitted_notional:
                remaining_cash -= outcome.submitted_notional
            outcomes.append(outcome)
        elif action.action == "TRIM":
            outcomes.append(_apply_trim(client, action))
        elif action.action == "CLOSE":
            outcomes.append(_apply_close(client, action))
        else:
            outcomes.append(
                ActionOutcome(
                    action=action,
                    outcome=Outcome.SKIPPED_INVALID,
                    detail=f"unknown action {action.action!r}",
                )
            )
    return outcomes
