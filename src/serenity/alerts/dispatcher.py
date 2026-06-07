"""Dispatch — fans a message out to the active channel(s).

The active channel is picked from `ALERT_FALLBACK_CHANNEL`. If
`telegram` is selected but its credentials are missing, we fall back
to stdout with a warning so messages are never silently dropped.

`dispatch` accepts a plain `str` (or anything with a sensible
`__str__`, like an `Alert`). Channels only ever see the final string.

Frequency policy lives here too: when MESSAGE_FREQUENCY=daily,
Alert messages are appended to the EventLog instead of going out
immediately. The scheduler calls `flush_daily_summary` at the
configured time to drain and deliver. Plain strings and `force=True`
calls (crashes) always go out immediately — out-of-band stuff
shouldn't get summarized.
"""

import logging
import traceback

from serenity.alerts.base import Alert, AlertChannel
from serenity.alerts.event_log import default_log
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


def dispatch(message: object, *, force: bool = False) -> None:
    """Send `message` to every active channel.

    `message` may be a string, an `Alert`, or anything with `__str__`.
    Errors are logged but never raised — alerts must not crash callers
    in the trading loop, no matter what's broken downstream (disk full,
    bad settings, channel API down).

    If MESSAGE_FREQUENCY=daily and `message` is an `Alert`, the alert
    is buffered to the EventLog instead of being delivered now —
    unless `force=True` (used for out-of-band notices like crashes).
    Plain strings always go out immediately.
    """
    try:
        settings = load_settings()
        is_alert = isinstance(message, Alert)
        # INFO-level so it shows up in Railway logs without bumping verbosity.
        # Lets users correlate a per-trade message arriving with which branch
        # the dispatcher actually took — the only reliable way to diagnose
        # "I'm in daily mode but getting per-tweet messages" from production.
        log.info(
            "dispatch: frequency=%s alert=%s force=%s -> %s",
            settings.message_frequency,
            is_alert,
            force,
            "BUFFER" if (not force and is_alert and settings.message_frequency == "daily") else "SEND",
        )
        if not force and is_alert and settings.message_frequency == "daily":
            try:
                default_log().append(message)  # type: ignore[arg-type]
                return
            except Exception:
                # Disk full, read-only fs, etc. Better to deliver now
                # than to drop the alert silently.
                log.exception("Event log append failed; delivering immediately")

        text = str(message)
        for channel in active_channels():
            try:
                channel.send(text)
            except Exception:
                log.exception("Channel %s failed", channel.name)
    except Exception:
        log.exception("dispatch failed")


def flush_daily_summary() -> None:
    """Drain the event buffer and deliver one summary per active channel.

    Empty buffer still delivers — a daily heartbeat tells the user the
    bot is alive on quiet days; silence is ambiguous (no news vs. dead
    process). Channels render their own "no events" message. Per-channel
    render or send failures are logged and don't block other channels.
    """
    events = default_log().drain()

    for channel in active_channels():
        try:
            text = channel.render_summary(events)
            channel.send(text)
        except Exception:
            log.exception("Channel %s failed during daily summary", channel.name)


def notify_crash(exc: BaseException, *, where: str = "bot") -> None:
    """Best-effort: dispatch a system message about a crash. Never raises.

    Suitable as the last call before the process dies, so the user knows
    Railway (or whatever host) is about to restart / give up. Bypasses
    the daily buffer — a crash notice you'd see tomorrow is useless.
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
        dispatch(alert, force=True)
    except Exception:
        log.exception("notify_crash failed to dispatch")
