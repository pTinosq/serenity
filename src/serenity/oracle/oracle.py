"""Oracle — reads one piece of text, returns a TradeSignal.

Thin wrapper over the shared Agent harness. The system prompt lives at
sibling `prompt.md`; the structured output schema is derived from
`TradeSignal`. See `serenity.agents.base.Agent` for the underlying
OpenRouter wiring.
"""

from pathlib import Path

from serenity.agents.base import Agent, AgentError
from serenity.oracle.models import TradeSignal

PROMPT_PATH = Path(__file__).parent / "prompt.md"


class OracleError(AgentError):
    """Raised when the oracle cannot produce a trade signal."""


class Oracle(Agent[TradeSignal]):
    """A text-to-trade-signal interpreter."""

    name = "trade_signal"
    output_model = TradeSignal
    prompt_path = PROMPT_PATH

    def analyze(self, text: str) -> TradeSignal:
        """Read `text` and return the trade signal it implies."""
        try:
            return self.run(text)
        except AgentError as e:
            raise OracleError(str(e)) from e


def system_prompt() -> str:
    """Public accessor for the eval cache — keyed by prompt content."""
    return Oracle._read_prompt()
