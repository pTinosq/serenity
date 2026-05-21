from functools import lru_cache
from pathlib import Path

from openrouter import OpenRouter

from serenity.config import Settings, load_settings
from serenity.oracle.models import TradeSignal

PROMPT_PATH = Path(__file__).parent / "prompt.md"


class OracleError(RuntimeError):
    """Raised when the oracle cannot produce a trade signal."""


@lru_cache(maxsize=1)
def get_client() -> OpenRouter:
    settings = load_settings()
    return OpenRouter(api_key=settings.openrouter_api_key.get_secret_value())


@lru_cache(maxsize=1)
def system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def trade_signal_schema() -> dict:
    schema = TradeSignal.model_json_schema()
    schema["additionalProperties"] = False
    return schema


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
        client: OpenRouter | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.client = client or get_client()

    def analyze(self, text: str) -> TradeSignal:
        """Read `text` and return the trade signal it implies.

        Raises OracleError when the model returns no content or output
        that fails schema validation. OpenRouter SDK errors (auth, rate
        limit, network) propagate.
        """
        result = self.client.chat.send(
            model=self.settings.sentiment_model,
            messages=[
                {"role": "system", "content": system_prompt()},
                {"role": "user", "content": text},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "trade_signal",
                    "strict": True,
                    "schema": trade_signal_schema(),
                },
            },
        )
        content = result.choices[0].message.content
        if not content:
            raise OracleError("Model returned no content")
        try:
            return TradeSignal.model_validate_json(content)
        except ValueError as e:
            raise OracleError(f"Failed to parse model output: {e}") from e
