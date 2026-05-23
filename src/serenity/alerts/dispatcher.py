"""Alert dispatch — fans an Alert out to the active channel(s).

The active channel is picked from `ALERT_FALLBACK_CHANNEL`. If
`telegram` is selected but its credentials are missing, we fall back
to stdout with a warning so alerts are never silently dropped.
"""

from __future__ import annotations

import logging
import traceback

from serenity.alerts.base import Alert, AlertChannel
from serenity.alerts.stdout import StdoutChannel
from serenity.alerts.telegram import TelegramChannel
from serenity.config import load_settings

log = logging.getLogger(__name__)

# Telegram caps messages at 4096 chars; leave headroom for the
# title/reason wrapper and HTML tags.
MAX_DETAIL_CHARS = 3500


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


def dispatch(alert: Alert) -> None:
    """Send `alert` to every active channel. Per-channel errors are logged
    but never raised — one broken channel must not silence the others."""
    for channel in active_channels():
        try:
            channel.send(alert)
        except Exception:
            log.exception("Alert channel %s failed", channel.name)


def notify_crash(exc: BaseException, *, where: str = "bot") -> None:
    """Best-effort: dispatch a system alert about a crash. Never raises.

    Suitable as the last call before the process dies, so the user knows
    Railway (or whatever host) is about to restart / give up.
    """
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    # Keep the tail — that's where the actual error lives.
    detail = tb if len(tb) <= MAX_DETAIL_CHARS else "…\n" + tb[-MAX_DETAIL_CHARS:]
    alert = Alert(
        reason="bot_crashed",
        title=f"Serenity crashed in {where}",
        detail=detail,
    )
    try:
        dispatch(alert)
    except Exception:
        log.exception("notify_crash failed to dispatch alert")
