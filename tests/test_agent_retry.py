"""Retry behavior for the Agent harness.

Transient OpenRouter errors (rate limits, 5xx, the malformed-success-body
shape that hides a provider 429) should retry with backoff. Non-transient
errors and exhausted retries should surface as AgentError so the bot loop's
per-tweet skip path absorbs them instead of crashing.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openrouter.errors import (
    OpenRouterError,
    ResponseValidationError,
    TooManyRequestsResponseError,
    UnauthorizedResponseError,
)
from pydantic import BaseModel

from serenity.agents.base import Agent, AgentError


class _Out(BaseModel):
    answer: str


class _TestAgent(Agent[_Out]):
    name = "test_agent"
    output_model = _Out
    retry_base_seconds = 0.0  # keep tests fast


def _fake_response() -> SimpleNamespace:
    """Mimic the OpenRouter response shape Agent.run consumes."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content='{"answer":"ok"}'))
        ]
    )


def _make_err(cls: type[OpenRouterError], status: int) -> OpenRouterError:
    """Build an SDK error instance without invoking its (strict) generated __init__.

    The generated constructors require typed `data` objects we don't have on
    hand in tests; OpenRouterError.__init__ alone is enough for the harness's
    isinstance-based retry routing.
    """
    err = cls.__new__(cls)
    raw = httpx.Response(status_code=status, request=httpx.Request("POST", "http://x"))
    OpenRouterError.__init__(err, f"status={status}", raw, None)
    return err


def test_retries_then_succeeds(settings) -> None:
    client = MagicMock()
    client.chat.send.side_effect = [
        _make_err(TooManyRequestsResponseError, 429),
        _fake_response(),
    ]
    with patch.object(_TestAgent, "_read_prompt", return_value="system"), \
         patch("serenity.agents.base.time.sleep") as sleep:
        agent = _TestAgent(settings=settings, client=client)
        out = agent.run("hi")
    assert out.answer == "ok"
    assert client.chat.send.call_count == 2
    sleep.assert_called_once()


def test_retries_on_responsevalidationerror(settings) -> None:
    """The actual shape that crashed prod: a provider 429 wrapped in a 200 body."""
    client = MagicMock()
    client.chat.send.side_effect = [
        _make_err(ResponseValidationError, 429),
        _fake_response(),
    ]
    with patch.object(_TestAgent, "_read_prompt", return_value="system"), \
         patch("serenity.agents.base.time.sleep"):
        agent = _TestAgent(settings=settings, client=client)
        assert agent.run("hi").answer == "ok"


def test_exhausts_retries_and_raises_agenterror(settings) -> None:
    client = MagicMock()
    client.chat.send.side_effect = _make_err(TooManyRequestsResponseError, 429)
    with patch.object(_TestAgent, "_read_prompt", return_value="system"), \
         patch("serenity.agents.base.time.sleep"):
        agent = _TestAgent(settings=settings, client=client)
        with pytest.raises(AgentError, match="after 3 attempts"):
            agent.run("hi")
    assert client.chat.send.call_count == 3


def test_non_retryable_error_fails_immediately(settings) -> None:
    """401 auth failures shouldn't retry — they won't fix themselves."""
    client = MagicMock()
    client.chat.send.side_effect = _make_err(UnauthorizedResponseError, 401)
    with patch.object(_TestAgent, "_read_prompt", return_value="system"), \
         patch("serenity.agents.base.time.sleep") as sleep:
        agent = _TestAgent(settings=settings, client=client)
        with pytest.raises(AgentError):
            agent.run("hi")
    assert client.chat.send.call_count == 1
    sleep.assert_not_called()
