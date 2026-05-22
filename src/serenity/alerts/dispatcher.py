"""Alert dispatch — fans an Alert out to every active channel.

Channel selection is hard-coded to stdout for now. As telegram /
discord / etc. land, `active_channels` will check settings and
include them when the relevant credentials are configured.
"""

from __future__ import annotations

import logging

from serenity.alerts.base import Alert, AlertChannel
from serenity.alerts.stdout import StdoutChannel

log = logging.getLogger(__name__)


def active_channels() -> list[AlertChannel]:
    return [StdoutChannel()]


def dispatch(alert: Alert) -> None:
    """Send `alert` to every active channel. Per-channel errors are logged
    but never raised — one broken channel must not silence the others."""
    for channel in active_channels():
        try:
            channel.send(alert)
        except Exception:
            log.exception("Alert channel %s failed", channel.name)
