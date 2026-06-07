"""TradeExecutor — turns one Oracle signal into a TradePlan.

The Oracle reads the tweet and identifies the signal. The TradeExecutor
sees the same tweet plus the signal plus the current portfolio plus
available cash, and decides the concrete actions.

The agent's prompt holds the policy. The runner enforces hard guards
on top (cash check, position cap, etc.) so a misbehaving LLM can't blow
the account up.
"""

from pathlib import Path

from serenity.agents.base import Agent, AgentError
from serenity.executor.models import TradePlan
from serenity.oracle.models import TradeSignal
from serenity.portfolio.snapshot import PortfolioPosition


class TradeExecutorError(AgentError):
    """Raised when the executor cannot produce a valid plan."""


def format_context(
    tweet: str,
    signal: TradeSignal,
    positions: list[PortfolioPosition],
    available_cash: float,
    min_trade_usd: float,
    max_trade_usd: float,
    max_position_usd: float,
) -> str:
    """Compose the executor's user message from the structured inputs.

    Plain text so the model can pick up the natural-language tweet
    alongside the JSON-shaped numerics — no nested escaping, no
    serialization tax.
    """
    if positions:
        portfolio_lines = [
            (
                f"- {p.ticker}: {p.side} {p.qty:g} shares @ ${p.avg_entry_price:.2f} avg, "
                f"${p.market_value:.2f} mkt value, "
                f"{p.unrealized_pl:+.2f} ({p.unrealized_plpc * 100:+.1f}%), "
                f"{p.portfolio_fraction * 100:.1f}% of book"
            )
            for p in positions
        ]
        portfolio_block = "\n".join(portfolio_lines)
    else:
        portfolio_block = "(empty — no open positions)"

    return (
        "TWEET:\n"
        f"{tweet.strip()}\n\n"
        "ORACLE SIGNAL:\n"
        f"  ticker: {signal.ticker}\n"
        f"  direction: {signal.order_type}\n"
        f"  confidence: {signal.confidence:.2f}\n"
        f"  sentiment: {signal.sentiment:.2f}\n\n"
        f"AVAILABLE CASH: ${available_cash:.2f}\n\n"
        "CURRENT PORTFOLIO:\n"
        f"{portfolio_block}\n\n"
        "RISK BOUNDS:\n"
        f"  MIN_TRADE_USD: ${min_trade_usd:.2f}\n"
        f"  MAX_TRADE_USD: ${max_trade_usd:.2f}\n"
        f"  MAX_POSITION_USD: ${max_position_usd:.2f}\n"
    )


class TradeExecutor(Agent[TradePlan]):
    """Per-tweet trade-planning agent."""

    name = "trade_plan"
    output_model = TradePlan
    prompt_path = Path(__file__).parent / "prompt.md"

    def decide(
        self,
        *,
        tweet: str,
        signal: TradeSignal,
        positions: list[PortfolioPosition],
        available_cash: float,
    ) -> TradePlan:
        """Return the executor's plan for this signal in this portfolio context."""
        message = format_context(
            tweet=tweet,
            signal=signal,
            positions=positions,
            available_cash=available_cash,
            min_trade_usd=self.settings.min_trade_usd,
            max_trade_usd=self.settings.max_trade_usd,
            max_position_usd=self.settings.max_position_usd,
        )
        try:
            return self.run(message)
        except AgentError as e:
            raise TradeExecutorError(str(e)) from e
