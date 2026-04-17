"""Order and trade models."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class Order(BaseModel):
    id: str
    market_id: str
    platform: str
    side: OrderSide
    outcome: str          # "yes" or "no"
    contracts: float = Field(gt=0)
    limit_price: float = Field(gt=0, le=1.0)
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    filled_at: datetime | None = None
    fill_price: float | None = None
    paper: bool = True


class Trade(BaseModel):
    order: Order
    pnl: float | None = None   # filled in after resolution
    resolved_at: datetime | None = None
