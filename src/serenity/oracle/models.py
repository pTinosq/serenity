from typing import Literal

from pydantic import BaseModel, Field

OrderType = Literal["BUY", "SELL", "N/A"]


class TradeSignal(BaseModel):
    """The trading action implied by a piece of text."""

    ticker: str = Field(
        description=(
            "Ticker symbol explicitly mentioned in the text (e.g. NVDA, AAPL), "
            "or very confidently inferred from a well-known company name. "
            'Use "N/A" when no ticker can be identified.'
        )
    )
    order_type: OrderType = Field(
        description=(
            "BUY if the text implies bullish action on the ticker. SELL if "
            "bearish. N/A when the text does not give enough to act on — no "
            "ticker, ambiguous sentiment, observational, or multiple tickers "
            'with no dominant subject. When ticker is "N/A", order_type '
            'must also be "N/A".'
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "How clearly the text supports the chosen order_type, on a 0.0-1.0 "
            'scale. Higher = more clear. Must be 0.0 when order_type is "N/A".'
        ),
    )
