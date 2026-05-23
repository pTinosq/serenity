"""Telegram alert channel.

Sends a single message per alert via the Bot API's `sendMessage`
endpoint. Uses HTML parse mode so we get bold/mono formatting without
worrying about MarkdownV2's exhaustive escape rules.

Setup:
1. Create a bot via @BotFather, copy the token into TELEGRAM_BOT_TOKEN.
2. DM your new bot any message so it can see you.
3. Visit https://api.telegram.org/bot<TOKEN>/getUpdates and copy the
   `chat.id` into TELEGRAM_CHAT_ID.
"""

from __future__ import annotations

import html
import json
import logging
from urllib import request
from urllib.error import URLError

from serenity.alerts.base import Alert
from serenity.config import Settings

log = logging.getLogger(__name__)

API_URL = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT_SECONDS = 10


class TelegramChannel:
    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    @classmethod
    def from_settings(cls, settings: Settings) -> "TelegramChannel | None":
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            return None
        return cls(
            bot_token=settings.telegram_bot_token.get_secret_value(),
            chat_id=settings.telegram_chat_id,
        )

    def send(self, alert: Alert) -> None:
        text = format_message(alert)
        payload = json.dumps({
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }).encode("utf-8")

        req = request.Request(
            API_URL.format(token=self.bot_token),
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except URLError as e:
            raise RuntimeError(f"Telegram request failed: {e}") from e

        result = json.loads(body)
        if not result.get("ok"):
            raise RuntimeError(
                f"Telegram API rejected message: {result.get('description', body)}"
            )


def format_message(alert: Alert) -> str:
    parts = [f"<b>⚠ {html.escape(alert.title)}</b>", ""]
    if alert.signal is not None:
        sig = alert.signal
        parts += [
            f"<b>Ticker:</b> <code>{html.escape(sig.ticker)}</code>",
            f"<b>Action:</b> {html.escape(sig.order_type)}",
        ]
        if alert.amount is not None:
            parts.append(f"<b>Amount:</b> ${alert.amount:.2f}")
        parts += [
            f"<b>Confidence:</b> {sig.confidence:.2f}",
            f"<b>Sentiment:</b> {sig.sentiment:.2f}",
        ]
    parts.append(f"<b>Reason:</b> <code>{html.escape(alert.reason)}</code>")
    if alert.tweet:
        parts += ["", "<b>Tweet:</b>", f"<blockquote>{html.escape(alert.tweet)}</blockquote>"]
    if alert.detail:
        parts += ["", html.escape(alert.detail)]
    return "\n".join(parts)
