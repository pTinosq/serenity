"""Generic LLM agent: prompt + output schema → callable.

Every LLM-driven component (Oracle, TradeExecutor, future portfolio
agents) inherits from `Agent`. Subclasses typically:

  1. Override `output_model` and `name` as class attributes
  2. Point `prompt_path` at a sibling `.md` file
  3. Expose a domain-specific method that formats the user message
     and calls `self.run(user_message)`

The base class owns the OpenRouter wiring, structured-output schema
locking, error handling, and response parsing — so subclasses are
tiny.
"""

import logging
import random
import time
from functools import lru_cache
from pathlib import Path
from typing import Generic, TypeVar

from openrouter import OpenRouter
from openrouter.errors import (
    BadGatewayResponseError,
    EdgeNetworkTimeoutResponseError,
    InternalServerResponseError,
    NoResponseError,
    OpenRouterError,
    ProviderOverloadedResponseError,
    RequestTimeoutResponseError,
    ResponseValidationError,
    ServiceUnavailableResponseError,
    TooManyRequestsResponseError,
)
from pydantic import BaseModel

from serenity.config import Settings, load_settings

log = logging.getLogger(__name__)

OutputT = TypeVar("OutputT", bound=BaseModel)

# Errors we'll retry on. Excludes auth (401/403), bad request (400),
# payload-too-large (413), unprocessable-entity (422), not-found (404) —
# those won't fix themselves by waiting.
#
# ResponseValidationError is in the list because in practice that's how a
# provider 429 reaches us: OpenRouter returns 200 with an `error` body the
# SDK can't deserialize. See the original crash that motivated this code.
RETRYABLE_OPENROUTER_ERRORS: tuple[type[OpenRouterError], ...] = (
    TooManyRequestsResponseError,
    ServiceUnavailableResponseError,
    ProviderOverloadedResponseError,
    RequestTimeoutResponseError,
    EdgeNetworkTimeoutResponseError,
    BadGatewayResponseError,
    InternalServerResponseError,
    ResponseValidationError,
    NoResponseError,
)


class AgentError(RuntimeError):
    """Raised when an agent cannot produce a valid output."""


@lru_cache(maxsize=1)
def shared_client() -> OpenRouter:
    """Process-wide OpenRouter client. All agents share this by default."""
    return OpenRouter(api_key=load_settings().openrouter_api_key.get_secret_value())


def _lock_down(node: object) -> None:
    """Recursively set additionalProperties=False on every object schema.

    OpenAI / OpenRouter strict structured output requires this on every
    nested object, not just the root. Pydantic omits it by default.
    """
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            node.setdefault("additionalProperties", False)
        for value in node.values():
            _lock_down(value)
    elif isinstance(node, list):
        for item in node:
            _lock_down(item)


class Agent(Generic[OutputT]):
    """An LLM agent that returns structured Pydantic output.

    Subclass with:

        class MyAgent(Agent[MyOutput]):
            name = "my_agent"
            output_model = MyOutput
            prompt_path = Path(__file__).parent / "my_prompt.md"

            def do_thing(self, x: str) -> MyOutput:
                return self.run(x)
    """

    # Subclasses set these. Defaults exist only so type-checkers don't complain.
    name: str = "agent"
    output_model: type[BaseModel] = BaseModel  # type: ignore[assignment]
    prompt_path: Path = Path(__file__).parent / "prompt.md"

    # Retry tuning. 3 attempts at 4s/8s/16s base ≈ 28s worst-case wall time
    # before giving up — long enough to ride out a typical rate-limit window,
    # short enough that we're not blocking the tweet stream for minutes.
    max_attempts: int = 3
    retry_base_seconds: float = 4.0

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: OpenRouter | None = None,
        model: str | None = None,
        temperature: float = 0.1,
    ) -> None:
        self.settings = settings or load_settings()
        self.client = client or shared_client()
        self.model = model or self.settings.sentiment_model
        self.temperature = temperature

    @classmethod
    @lru_cache(maxsize=8)
    def _read_prompt(cls) -> str:
        return cls.prompt_path.read_text(encoding="utf-8")

    @classmethod
    @lru_cache(maxsize=8)
    def _schema(cls) -> dict:
        schema = cls.output_model.model_json_schema()
        _lock_down(schema)
        return schema

    def run(self, user_message: str) -> OutputT:
        """Send `user_message` to the model and return validated output.

        Transient OpenRouter failures (rate limits, 5xx, provider overload,
        the malformed-success-body shape that hides a provider 429) are
        retried with exponential backoff + jitter. Non-transient SDK errors
        and exhausted retries surface as AgentError so the caller's per-tweet
        skip path absorbs them.
        """
        result = self._call_with_retry(user_message)
        content = result.choices[0].message.content
        if not content:
            raise AgentError(f"{self.name}: model returned no content")
        try:
            return self.output_model.model_validate_json(content)  # type: ignore[return-value]
        except ValueError as e:
            raise AgentError(f"{self.name}: failed to parse model output: {e}") from e

    def _call_with_retry(self, user_message: str):
        request = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": self._read_prompt()},
                {"role": "user", "content": user_message},
            ],
            temperature=self.temperature,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": self.name,
                    "strict": True,
                    "schema": self._schema(),
                },
            },
        )
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self.client.chat.send(**request)
            except RETRYABLE_OPENROUTER_ERRORS as e:
                if attempt == self.max_attempts:
                    raise AgentError(
                        f"{self.name}: OpenRouter call failed after "
                        f"{self.max_attempts} attempts: {e}"
                    ) from e
                delay = self.retry_base_seconds * (2 ** (attempt - 1))
                delay += random.uniform(0, delay * 0.25)
                log.warning(
                    "%s: %s on attempt %d/%d, retrying in %.1fs",
                    self.name, type(e).__name__, attempt, self.max_attempts, delay,
                )
                time.sleep(delay)
            except OpenRouterError as e:
                raise AgentError(f"{self.name}: OpenRouter call failed: {e}") from e
