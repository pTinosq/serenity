"""Pin down the daily-mode buffering invariants for the dispatcher.

These tests exist because a user reported per-trade messages arriving
in daily mode AND an empty end-of-day summary at the same time —
mutually exclusive symptoms by the dispatcher's design. The tests
prove the design works in isolation; production breakage is therefore
either environmental (settings not actually `daily` at dispatch time)
or a regression these tests will now catch.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from serenity.alerts.base import Alert
from serenity.alerts import dispatcher
from serenity.alerts.event_log import EventLog


@pytest.fixture(autouse=True)
def reset_buffer_warning():
    """The buffer-broken warning is one-shot per process; reset between tests."""
    dispatcher._buffer_warning_sent = False
    yield
    dispatcher._buffer_warning_sent = False


class FakeChannel:
    """Records what was sent, so tests can assert delivery vs. buffering."""

    name = "fake"

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.summaries: list[str] = []

    def send(self, text: str) -> None:
        self.sent.append(text)

    def render_summary(self, events: list) -> str:
        out = f"summary:{len(events)}"
        self.summaries.append(out)
        return out


@pytest.fixture
def fake_channel(monkeypatch) -> FakeChannel:
    ch = FakeChannel()
    monkeypatch.setattr(dispatcher, "active_channels", lambda: [ch])
    return ch


@pytest.fixture
def tmp_log(tmp_path, monkeypatch) -> EventLog:
    """Point the dispatcher's default EventLog at a tmp file."""
    log = EventLog(path=tmp_path / "events.jsonl")
    monkeypatch.setattr(dispatcher, "default_log", lambda: log)
    return log


def make_settings(frequency: str):
    """Build a settings object the dispatcher's frequency check will accept."""
    class S:
        message_frequency = frequency
        alert_fallback_channel = "stdout"
        telegram_bot_token = None
        telegram_chat_id = None
    return S()


def test_daily_mode_buffers_alerts_does_not_send(fake_channel, tmp_log) -> None:
    with patch.object(dispatcher, "load_settings", return_value=make_settings("daily")):
        dispatcher.dispatch(Alert(reason="trade_executed", title="BUY 100 XYZ"))

    assert fake_channel.sent == [], "Alert was delivered immediately in daily mode"
    assert tmp_log.path.exists(), "Buffer file was not created"
    lines = tmp_log.path.read_text().strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["alert"]["reason"] == "trade_executed"


def test_per_tweet_mode_sends_immediately(fake_channel, tmp_log) -> None:
    with patch.object(dispatcher, "load_settings", return_value=make_settings("per-tweet")):
        dispatcher.dispatch(Alert(reason="trade_executed", title="BUY 100 XYZ"))

    assert len(fake_channel.sent) == 1
    assert not tmp_log.path.exists() or tmp_log.path.read_text() == ""


def test_daily_mode_with_force_bypasses_buffer(fake_channel, tmp_log) -> None:
    """notify_crash uses force=True; crashes shouldn't wait for the daily slot."""
    with patch.object(dispatcher, "load_settings", return_value=make_settings("daily")):
        dispatcher.dispatch(Alert(reason="bot_crashed", title="oops"), force=True)

    assert len(fake_channel.sent) == 1
    assert not tmp_log.path.exists() or tmp_log.path.read_text() == ""


def test_daily_mode_string_message_sends_immediately(fake_channel, tmp_log) -> None:
    """Plain-string dispatches are out-of-band; only Alert objects get buffered."""
    with patch.object(dispatcher, "load_settings", return_value=make_settings("daily")):
        dispatcher.dispatch("Hello world")

    assert fake_channel.sent == ["Hello world"]


def test_daily_mode_buffer_drains_on_flush(fake_channel, tmp_log) -> None:
    """End-to-end: append several events, flush, expect summary delivered + buffer cleared."""
    with patch.object(dispatcher, "load_settings", return_value=make_settings("daily")):
        dispatcher.dispatch(Alert(reason="trade_executed", title="BUY 100 XYZ"))
        dispatcher.dispatch(Alert(reason="trade_executed", title="BUY 200 ABC"))

    assert fake_channel.sent == []  # buffered, not sent

    with patch.object(dispatcher, "load_settings", return_value=make_settings("daily")):
        dispatcher.flush_daily_summary()

    assert fake_channel.summaries == ["summary:2"]
    assert fake_channel.sent == ["summary:2"]
    # Buffer cleared after flush
    assert tmp_log.path.read_text() == ""


def test_append_failure_falls_back_with_one_time_warning(fake_channel, tmp_log, monkeypatch) -> None:
    """If the buffer write fails, the alert reaches the user AND they get a one-time
    'buffer broken' warning so they understand why per-tweet messages are appearing.
    """

    def broken_append(_alert):
        raise OSError("disk full")

    monkeypatch.setattr(tmp_log, "append", broken_append)

    with patch.object(dispatcher, "load_settings", return_value=make_settings("daily")):
        dispatcher.dispatch(Alert(reason="trade_executed", title="BUY 100 XYZ"))
        # Second dispatch on the same broken buffer: no second warning.
        dispatcher.dispatch(Alert(reason="trade_executed", title="BUY 200 ABC"))

    # 2 trade alerts + 1 buffer-broken warning (only fires on first failure)
    assert len(fake_channel.sent) == 3
    assert any("buffer is broken" in msg.lower() for msg in fake_channel.sent), (
        f"Expected a buffer-broken warning among {fake_channel.sent!r}"
    )
