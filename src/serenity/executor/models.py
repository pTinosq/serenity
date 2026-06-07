from typing import Literal

from pydantic import BaseModel, Field

ActionType = Literal["BUY", "TRIM", "CLOSE", "HOLD"]


class TradeAction(BaseModel):
    """One concrete trade the executor decided on.

    HOLD means "explicitly do nothing for this ticker"; it's used to
    record that the executor saw a position and chose not to touch it.
    The runner filters HOLD out before submitting orders.
    """

    ticker: str = Field(description="US-listed ticker symbol the action targets.")
    action: ActionType = Field(
        description=(
            "BUY: open or add to a long position (specify notional_usd). "
            "TRIM: sell a fraction of an existing position (specify trim_fraction). "
            "CLOSE: liquidate the entire existing position. "
            "HOLD: deliberately take no action on this ticker."
        )
    )
    notional_usd: float | None = Field(
        default=None,
        description=(
            "USD notional for BUY actions. Must be >= MIN_TRADE_USD and "
            "<= MAX_TRADE_USD and <= available_cash. Null for TRIM/CLOSE/HOLD."
        ),
    )
    trim_fraction: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Fraction (0.0, 1.0) of the existing position to sell on TRIM. "
            "Prefer round values: 0.25, 0.33, 0.5, 0.66, 0.75. Null otherwise."
        ),
    )
    reasoning: str = Field(
        description=(
            "One short sentence citing the specific data points that drove "
            "the decision (conviction level, existing position size, cash "
            "available, P&L)."
        )
    )


class TradePlan(BaseModel):
    """The executor's response to one incoming signal."""

    actions: list[TradeAction] = Field(
        description=(
            "List of concrete actions to execute. May be empty when the "
            "right move is to do nothing at all. Usually 0 or 1 actions; "
            "more than 2 is unusual and the reasoning had better be solid."
        )
    )
    summary: str = Field(
        description="One sentence framing the overall response to this signal."
    )
