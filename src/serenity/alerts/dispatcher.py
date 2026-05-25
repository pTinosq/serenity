"""Dispatch — fans a message out to the active channel(s).

The active channel is picked from `ALERT_FALLBACK_CHANNEL`. If
`telegram` is selected but its credentials are missing, we fall back
to stdout with a warning so messages are never silently dropped.

`dispatch` accepts a plain `str` (or anything with a sensible
`__str__`, like an `Alert`). Channels only ever see the final string.
"""

from __future__ import annotations

import logging
import traceback

from serenity.alerts.base import Alert, AlertChannel
from serenity.alerts.stdout import StdoutChannel
from serenity.alerts.telegram import TelegramChannel
from serenity.config import load_settings

log = logging.getLogger(__name__)

# Telegram caps messages at 4096 chars; leave headroom.
MAX_MESSAGE_CHARS = 3500


def active_channels() -> list[AlertChannel]:
    settings = load_settings()
    if settings.alert_fallback_channel == "telegram":
        telegram = TelegramChannel.from_settings(settings)
        if telegram is not None:
            return [telegram]
        log.warning(
            "ALERT_FALLBACK_CHANNEL=telegram but TELEGRAM_BOT_TOKEN / "
            "TELEGRAM_CHAT_ID are not set — falling back to stdout"
        )
    return [StdoutChannel()]


def dispatch(message: object) -> None:
    """Send `message` (a string, Alert, or anything with __str__) to every
    active channel. Per-channel errors are logged but never raised."""
    text = str(message)
    for channel in active_channels():
        try:
            channel.send(text)
        except Exception:
            log.exception("Channel %s failed", channel.name)


def notify_crash(exc: BaseException, *, where: str = "bot") -> None:
    """Best-effort: dispatch a system message about a crash. Never raises.

    Suitable as the last call before the process dies, so the user knows
    Railway (or whatever host) is about to restart / give up.
    """
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    # Keep the tail — that's where the actual error lives.
    detail = tb if len(tb) <= MAX_MESSAGE_CHARS else "…\n" + tb[-MAX_MESSAGE_CHARS:]
    alert = Alert(
        reason="bot_crashed",
        title=f"Serenity crashed in {where}",
        detail=detail,
    )
    try:
        dispatch(alert)
    except Exception:
        log.exception("notify_crash failed to dispatch")
