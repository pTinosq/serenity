"""Alert data model and channel protocol.

An `Alert` is a user-facing notice — typically something the bot
*can't* act on but the human might want to act on (e.g. a strong
signal on a ticker Alpaca can't route). Channels (stdout, telegram,
discord, ...) are responsible for surfacing it through their medium.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from serenity.oracle.models import TradeSignal


@dataclass
class Alert:
    reason: str                          # short tag, e.g. "not_tradeable"
    title: str                           # one-line headline shown to the user
    detail: str = ""                     # optional extra context / body / traceback
    signal: TradeSignal | None = None    # signal that prompted the alert, if any
    amount: float | None = None          # sized notional in USD, if known
    tweet: str | None = None             # source tweet/text that produced the signal


class AlertChannel(Protocol):
    """Surface alerts through some medium. Implementations may raise on
    delivery failure; the dispatcher catches anything that escapes."""

    name: str

    def send(self, alert: Alert) -> None: ...
