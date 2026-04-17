"""Core market data model."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Platform(str, Enum):
    POLYMARKET = "polymarket"
    KALSHI = "kalshi"
    UNKNOWN = "unknown"


class MarketOutcome(BaseModel):
    id: str
    name: str
    probability: float = Field(ge=0.0, le=1.0)  # market-implied probability
    price: float = Field(ge=0.0, le=1.0)         # last traded price (same as prob for binary)
    volume: float = 0.0


class Market(BaseModel):
    id: str
    platform: Platform
    question: str
    description: str = ""
    category: str = ""
    outcomes: list[MarketOutcome]
    volume_usd: float = 0.0
    liquidity_usd: float = 0.0
    close_time: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @property
    def is_binary(self) -> bool:
        return len(self.outcomes) == 2

    @property
    def yes_probability(self) -> float | None:
        """Convenience: market-implied YES probability for binary markets."""
        if not self.is_binary:
            return None
        for o in self.outcomes:
            if o.name.upper() in ("YES", "TRUE", "1"):
                return o.probability
        return self.outcomes[0].probability

    @property
    def days_to_close(self) -> float | None:
        if self.close_time is None:
            return None
        delta = self.close_time - datetime.utcnow()
        return max(delta.total_seconds() / 86_400, 0)
