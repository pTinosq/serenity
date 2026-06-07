"""LLM-backed portfolio reviewer.

Wraps OpenRouter the same way `Oracle` does: process-wide client cache,
structured-output enforced via JSON schema, system prompt loaded from
a sibling `prompt.md`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from openrouter import OpenRouter

from serenity.config import Settings, load_settings
from serenity.portfolio.models import PortfolioPosition, PortfolioReview

PROMPT_PATH = Path(__file__).parent / "prompt.md"


class PortfolioReviewError(RuntimeError):
    """Raised when the reviewer cannot produce a valid PortfolioReview."""


@lru_cache(maxsize=1)
def get_client() -> OpenRouter:
    settings = load_settings()
    return OpenRouter(api_key=settings.openrouter_api_key.get_secret_value())


@lru_cache(maxsize=1)
def system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _lock_down(node: dict) -> None:
    """Recursively set additionalProperties=False on every object schema.

    OpenAI/OpenRouter strict structured output requires it on every object,
    not just the root. Pydantic's generated schema omits it by default.
    """
    if not isinstance(node, dict):
        return
    if node.get("type") == "object" or "properties" in node:
        node.setdefault("additionalProperties", False)
    for value in node.values():
        if isinstance(value, dict):
            _lock_down(value)
        elif isinstance(value, list):
            for item in value:
                _lock_down(item)


@lru_cache(maxsize=1)
def review_schema() -> dict:
    schema = PortfolioReview.model_json_schema()
    _lock_down(schema)
    return schema


class PortfolioReviewer:
    """Reviews a portfolio snapshot and returns recommended actions."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: OpenRouter | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.client = client or get_client()

    def review(self, positions: list[PortfolioPosition]) -> PortfolioReview:
        """Return a HOLD/TRIM/CLOSE recommendation per position.

        Raises PortfolioReviewError when the model returns no content,
        emits unparsable output, or returns an action set that doesn't
        cover every input ticker exactly once.
        """
        if not positions:
            return PortfolioReview(
                actions=[],
                summary="Portfolio is empty. Nothing to review.",
            )

        payload = [p.model_dump() for p in positions]
        result = self.client.chat.send(
            model=self.settings.sentiment_model,
            messages=[
                {"role": "system", "content": system_prompt()},
                {"role": "user", "content": json.dumps(payload, indent=2)},
            ],
            temperature=0.1,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "portfolio_review",
                    "strict": True,
                    "schema": review_schema(),
                },
            },
        )
        content = result.choices[0].message.content
        if not content:
            raise PortfolioReviewError("Model returned no content")
        try:
            review = PortfolioReview.model_validate_json(content)
        except ValueError as e:
            raise PortfolioReviewError(f"Failed to parse model output: {e}") from e

        expected = {p.ticker for p in positions}
        actual = {a.ticker for a in review.actions}
        if expected != actual:
            missing = expected - actual
            extra = actual - expected
            raise PortfolioReviewError(
                f"Action coverage mismatch — missing: {sorted(missing)}, extra: {sorted(extra)}"
            )
        return review
