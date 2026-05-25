"""Alert data model and channel protocol.

An `Alert` is a structured user-facing notice — typically something
the bot can't act on but the human might want to act on. It renders
itself to plain text via `__str__`, which is what channels actually
deliver. Callers who just want to say something can pass a bare
string instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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

    def __str__(self) -> str:
        lines = [f"⚠ {self.title}", ""]
        if self.signal is not None:
            sig = self.signal
            headline = f"{sig.order_type} {sig.ticker}"
            if self.amount is not None:
                headline += f" — ${self.amount:.2f}"
            headline += f" (conf {sig.confidence:.2f}, sent {sig.sentiment:.2f})"
            lines.append(headline)
        lines.append(f"reason: {self.reason}")
        if self.tweet:
            lines += ["", f'"{self.tweet}"']
        if self.detail:
            lines += ["", self.detail]
        return "\n".join(lines)


@dataclass
class Event:
    """An `Alert` plus the UTC moment it was recorded.

    Kept here next to `Alert` because both are alert-domain value
    types — `Event` is what channels render in daily-summary mode
    (`AlertChannel.render_summary` takes `list[Event]`). The persistent
    JSONL buffer lives in `event_log.py`, but the shape of the data
    belongs with the rest of the alert vocabulary.
    """

    timestamp: datetime
    alert: Alert


class AlertChannel(Protocol):
    """Surface a message through some medium. Implementations may raise
    on delivery failure; the dispatcher catches anything that escapes.

    `send` ships an already-formatted string. `render_summary` turns a
    batch of buffered events (daily mode) into one such string —
    formatting is per-channel because what looks good in a terminal
    panel and what looks good on Telegram diverge.
    """

    name: str

    def send(self, text: str) -> None: ...

    def render_summary(self, events: list[Event]) -> str: ...
