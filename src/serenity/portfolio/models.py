from typing import Literal

from pydantic import BaseModel, Field

PositionSide = Literal["long", "short"]
ReviewAction = Literal["HOLD", "TRIM", "CLOSE"]


class PortfolioPosition(BaseModel):
    """One row of the user's current Alpaca book, as the reviewer sees it."""

    ticker: str
    side: PositionSide
    qty: float = Field(description="Signed share count. Negative for shorts.")
    avg_entry_price: float
    current_price: float
    market_value: float = Field(description="Signed. Negative for shorts.")
    unrealized_pl: float = Field(description="Profit/loss in USD.")
    unrealized_plpc: float = Field(description="Profit/loss as a fraction (0.10 = +10%).")
    portfolio_fraction: float = Field(
        ge=0.0,
        le=1.0,
        description="This position's |market_value| divided by total |market_value| across the book.",
    )


class PositionAction(BaseModel):
    """The reviewer's recommendation for one position."""

    ticker: str = Field(description="Must match a ticker in the input snapshot.")
    action: ReviewAction = Field(
        description=(
            "HOLD: keep the position untouched. TRIM: sell a fraction of it "
            "(specify trim_fraction). CLOSE: liquidate the entire position."
        )
    )
    trim_fraction: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Fraction of the position to sell when action is TRIM. Ignored "
            "when action is HOLD or CLOSE. Must be in (0.0, 1.0). Round "
            "numbers like 0.25, 0.33, 0.5 are preferred over fine-grained values."
        ),
    )
    reasoning: str = Field(
        description=(
            "One short sentence explaining the recommendation. Cite the "
            "specific data point (P&L, concentration) that drove it."
        )
    )


class PortfolioReview(BaseModel):
    """The reviewer's full output for one snapshot."""

    actions: list[PositionAction] = Field(
        description="Exactly one action per position in the input snapshot, in any order."
    )
    summary: str = Field(
        description=(
            "One or two sentences summarising the overall portfolio shape "
            "(concentration, net long vs short, dominant theme if visible)."
        )
    )
