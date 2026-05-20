from functools import lru_cache
from pathlib import Path

from openai import OpenAI

from serenity.config import Settings, load_settings
from serenity.oracle.models import TradeSignal

_PROMPT_PATH = Path(__file__).parent / "prompt.md"


class OracleError(RuntimeError):
    """Raised when the oracle cannot produce a trade signal."""


@lru_cache(maxsize=1)
def _get_client() -> OpenAI:
    settings = load_settings()
    return OpenAI(api_key=settings.openai_api_key.get_secret_value())


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


class Oracle:
    """A text-to-trade-signal interpreter.

    Reads a short piece of text (typically a tweet) and returns a
    structured TradeSignal describing the trade implied by that text.
    The underlying model, prompt, and structured-output wiring are
    hidden behind a single `analyze(text)` call.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: OpenAI | None = None,
    ) -> None:
        self._settings = settings or load_settings()
        self._client = client or _get_client()

    def analyze(self, text: str) -> TradeSignal:
        """Read `text` and return the trade signal it implies.

        Raises OracleError when the model refuses or returns no parsed
        output. OpenAI SDK errors (auth, rate limit, network) propagate.
        """
        completion = self._client.chat.completions.parse(
            model=self._settings.sentiment_model,
            messages=[
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": text},
            ],
            response_format=TradeSignal,
        )
        message = completion.choices[0].message
        if message.parsed is None:
            raise OracleError(message.refusal or "Model returned no parsed output")
        return message.parsed
