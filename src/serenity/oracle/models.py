from typing import Literal

from pydantic import BaseModel, Field

OrderType = Literal["BUY", "SELL", "NO_TRADE"]


class TradeSignal(BaseModel):
    """The trading action implied by a piece of text."""

    ticker: str | None = Field(
        description=(
            "Ticker symbol explicitly mentioned in the text (e.g. NVDA, AAPL). "
            "Null if the text mentions no specific ticker or company."
        )
    )
    order_type: OrderType = Field(
        description=(
            "BUY if the text implies bullish action on the ticker. "
            "SELL if bearish. NO_TRADE when the text does not give enough to "
            "act on — no ticker, ambiguous sentiment, observational, or "
            "multiple tickers with conflicting directions. If ticker is null, "
            "order_type must be NO_TRADE."
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "How clearly the text supports the chosen order_type, on a 0.0-1.0 "
            "scale. Higher = more clear. For NO_TRADE, this is the model's "
            "confidence that abstaining is the right call."
        ),
    )
