"""Open position tracking."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class PositionSide(str, Enum):
    YES = "yes"
    NO = "no"


class Position(BaseModel):
    id: str
    market_id: str
    platform: str
    side: PositionSide
    contracts: float = Field(gt=0)
    avg_entry_price: float = Field(gt=0, le=1.0)
    current_price: float = Field(gt=0, le=1.0)
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: datetime | None = None

    @property
    def cost_basis(self) -> float:
        return self.contracts * self.avg_entry_price

    @property
    def market_value(self) -> float:
        return self.contracts * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.cost_basis

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.cost_basis == 0:
            return 0.0
        return self.unrealized_pnl / self.cost_basis
