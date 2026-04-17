"""Abstract executor and shared trade record type."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TradeRecord:
    trade_id: str
    market_id: str
    platform: str
    side: str          # "yes" | "no"
    contracts: float
    fill_price: float
    size_usd: float
    paper: bool
    filled_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class BaseExecutor(ABC):

    @abstractmethod
    async def submit(
        self,
        market_id: str,
        platform: str,
        side: str,
        size_usd: float,
        limit_price: float,
    ) -> TradeRecord:
        ...
