from typing import Literal

from pydantic import BaseModel, Field

OrderType = Literal["BUY", "SELL"]


class TradeSignal(BaseModel):
    """The trading action implied by a piece of text."""

    ticker: str | None = Field(
        description=(
            "Ticker symbol explicitly mentioned in the text (e.g. NVDA, AAPL). "
            "Null if the text mentions no specific ticker or company."
        )
    )
    order_type: OrderType | None = Field(
        description=(
            "BUY if the text implies bullish action on the ticker, SELL if "
            "bearish. Null when there is no actionable signal."
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "How clearly the text points to this signal, on a 0.0-1.0 scale. "
            "0.0 when there is no signal."
        ),
    )
