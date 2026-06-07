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

from functools import lru_cache
from pathlib import Path
from typing import Generic, TypeVar

from openrouter import OpenRouter
from pydantic import BaseModel

from serenity.config import Settings, load_settings

OutputT = TypeVar("OutputT", bound=BaseModel)


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

        Raises AgentError on empty content or schema-violating output.
        Network / auth errors from the SDK propagate.
        """
        result = self.client.chat.send(
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
        content = result.choices[0].message.content
        if not content:
            raise AgentError(f"{self.name}: model returned no content")
        try:
            return self.output_model.model_validate_json(content)  # type: ignore[return-value]
        except ValueError as e:
            raise AgentError(f"{self.name}: failed to parse model output: {e}") from e
