"""Market scanner base class and shared data types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from src.logging_setup import get_logger

logger = get_logger(__name__)


class Market(BaseModel):
    id: str
    title: str
    platform: str = ""
    description: str = ""
    category: str = ""
    bid: float = Field(ge=0.0, le=1.0)
    ask: float = Field(ge=0.0, le=1.0)
    volume_usd: float = 0.0
    orderbook_depth: float = 0.0
    close_time: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @property
    def spread(self) -> float:
        """Bid/ask spread as a fraction of price."""
        return self.ask - self.bid

    @property
    def mid_price(self) -> float:
        """Midpoint of bid/ask — implied probability for binary markets."""
        return (self.bid + self.ask) / 2

    @property
    def days_to_close(self) -> float | None:
        if self.close_time is None:
            return None
        delta = self.close_time - datetime.now(timezone.utc)
        return max(delta.total_seconds() / 86_400, 0)


class BaseScanner(ABC):
    platform: str = "unknown"

    @abstractmethod
    async def fetch_all(self) -> list[Market]:
        """Return all active markets from the platform."""
        ...

    async def scan(self) -> list[Market]:
        """Fetch markets and log results."""
        markets = await self.fetch_all()
        logger.info(
            "scanner.fetched",
            platform=self.platform,
            count=len(markets),
        )
        return markets
