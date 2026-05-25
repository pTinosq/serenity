"""Persistent event buffer for daily-mode alerts.

When `MESSAGE_FREQUENCY=daily`, events are appended here instead of
being delivered immediately. The scheduler drains the log at the
configured time, hands the events to the active channel's
`render_summary`, and clears the buffer.

JSONL on disk so a redeploy or crash mid-day doesn't drop the
summary — a fresh instance picks up where the previous one left off.

Thread-safe: append() and drain() can race (bot loop appends from the
tweet handler; scheduler drains from a daemon thread).
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from serenity.alerts.base import Alert, Event
from serenity.oracle.models import TradeSignal

log = logging.getLogger(__name__)

DEFAULT_PATH = Path("data") / "event_log.jsonl"


class EventLog:
    """Append-only JSONL store with atomic drain.

    One file. A single lock guards both append and drain so the
    drain-then-truncate sequence can't race with a concurrent append
    (which would lose the racing event).
    """

    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        self.path = path
        self.lock = threading.Lock()

    def append(self, alert: Alert) -> None:
        event = Event(timestamp=datetime.now(timezone.utc), alert=alert)
        line = json.dumps(serialize(event), separators=(",", ":"))
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def drain(self) -> list[Event]:
        """Return all buffered events and clear the log atomically."""
        with self.lock:
            if not self.path.exists():
                return []
            raw = self.path.read_text(encoding="utf-8")
            # Truncate immediately so a concurrent append after drain
            # starts a fresh day rather than re-entering this batch.
            self.path.write_text("", encoding="utf-8")

        events: list[Event] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(deserialize(json.loads(line)))
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                log.warning("Skipping malformed event log line: %s — %s", e, line[:120])
        return events


def serialize(event: Event) -> dict:
    a = event.alert
    return {
        "timestamp": event.timestamp.isoformat(),
        "alert": {
            "reason": a.reason,
            "title": a.title,
            "detail": a.detail,
            "amount": a.amount,
            "tweet": a.tweet,
            "signal": a.signal.model_dump() if a.signal is not None else None,
        },
    }


def deserialize(data: dict) -> Event:
    a = data["alert"]
    sig = a.get("signal")
    return Event(
        timestamp=datetime.fromisoformat(data["timestamp"]),
        alert=Alert(
            reason=a["reason"],
            title=a["title"],
            detail=a.get("detail", ""),
            amount=a.get("amount"),
            tweet=a.get("tweet"),
            signal=TradeSignal(**sig) if sig else None,
        ),
    )


_default_log: EventLog | None = None


def default_log() -> EventLog:
    """Process-wide singleton, lazily constructed."""
    global _default_log
    if _default_log is None:
        _default_log = EventLog()
    return _default_log
