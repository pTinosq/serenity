"""Daily-summary scheduler — a daemon thread that fires once per day.

When MESSAGE_FREQUENCY=daily, the bot loop calls
`start_daily_scheduler()` once at startup. The thread computes the
next delivery moment (in UTC), sleeps until then, calls
`flush_daily_summary`, and loops. Daemon=True, so it dies with the
process — no explicit shutdown.

If the bot is restarted after the day's delivery time but before
midnight, the thread targets *tomorrow* — running a stale summary on
restart could spam the user with already-delivered content (or, more
subtly, miss new events that came in during the post-delivery
window). Wait for the next clean slot.
"""

import logging
import threading
import time as time_mod
from datetime import datetime, time, timedelta, timezone

from serenity.alerts.dispatcher import flush_daily_summary

log = logging.getLogger(__name__)


def next_delivery(now: datetime, delivery: time) -> datetime:
    """First moment >= now when the wall clock reads `delivery` in UTC.

    If `now` is already past today's slot, return tomorrow's. Equality
    counts as future — calling at exactly the slot fires today rather
    than waiting 24h.
    """
    today_slot = now.replace(
        hour=delivery.hour,
        minute=delivery.minute,
        second=0,
        microsecond=0,
    )
    if now <= today_slot:
        return today_slot
    return today_slot + timedelta(days=1)


def run_loop(delivery_hhmm: str) -> None:
    delivery = time.fromisoformat(delivery_hhmm)
    log.info("Daily summary scheduler armed for %s UTC", delivery_hhmm)
    while True:
        now = datetime.now(timezone.utc)
        target = next_delivery(now, delivery)
        sleep_seconds = (target - now).total_seconds()
        log.debug(
            "Daily scheduler sleeping %.0fs until %s UTC",
            sleep_seconds,
            target.isoformat(),
        )
        time_mod.sleep(max(sleep_seconds, 1.0))
        try:
            flush_daily_summary()
        except Exception:
            log.exception("flush_daily_summary failed; will retry next slot")


def start_daily_scheduler(delivery_hhmm: str) -> threading.Thread:
    thread = threading.Thread(
        target=run_loop,
        args=(delivery_hhmm,),
        name="daily-summary-scheduler",
        daemon=True,
    )
    thread.start()
    return thread
