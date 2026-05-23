"""Alert dispatch — fans an Alert out to the active channel(s).

The active channel is picked from `ALERT_FALLBACK_CHANNEL`. If
`telegram` is selected but its credentials are missing, we fall back
to stdout with a warning so alerts are never silently dropped.
"""

from __future__ import annotations

import logging

from serenity.alerts.base import Alert, AlertChannel
from serenity.alerts.stdout import StdoutChannel
from serenity.alerts.telegram import TelegramChannel
from serenity.config import load_settings

log = logging.getLogger(__name__)


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
