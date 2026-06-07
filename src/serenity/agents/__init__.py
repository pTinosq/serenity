"""Shared LLM-agent harness.

`Agent` is the base class every LLM-driven component in the bot inherits
from. Spinning up a new agent is one OOP instantiation: pick a name,
point at a prompt file, supply an output Pydantic model. No more
hand-rolled OpenRouter glue per agent.
"""

from serenity.agents.base import Agent, AgentError

__all__ = ["Agent", "AgentError"]
