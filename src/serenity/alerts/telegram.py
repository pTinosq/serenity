"""Telegram alert channel.

Sends a single message per call via the Bot API's `sendMessage`
endpoint. We don't set a parse_mode — the text we receive is treated
as-is, so callers don't have to think about HTML/Markdown escaping.

Setup:
1. Create a bot via @BotFather, copy the token into TELEGRAM_BOT_TOKEN.
2. DM your new bot any message so it can see you.
3. Visit https://api.telegram.org/bot<TOKEN>/getUpdates and copy the
   `chat.id` into TELEGRAM_CHAT_ID.
"""

from __future__ import annotations

import json
import logging
from urllib import request
from urllib.error import URLError

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

    def send(self, text: str) -> None:
        payload = json.dumps({
            "chat_id": self.chat_id,
            "text": text,
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
