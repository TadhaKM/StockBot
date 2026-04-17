"""Market scanner base class and shared data types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.config import cfg
from src.logging_setup import get_logger

logger = get_logger(__name__)


class Market(BaseModel):
    id: str
    platform: str
    question: str
    description: str = ""
    category: str = ""
    yes_probability: float = Field(ge=0.0, le=1.0)
    volume_usd: float = 0.0
    liquidity_usd: float = 0.0
    close_time: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @property
    def days_to_close(self) -> float | None:
        if self.close_time is None:
            return None
        delta = self.close_time - datetime.utcnow()
        return max(delta.total_seconds() / 86_400, 0)


class BaseScanner(ABC):
    platform: str = "unknown"

    @abstractmethod
    async def fetch_all(self) -> list[Market]:
        """Return all active markets from the platform (no filtering)."""
        ...

    async def scan(self) -> list[Market]:
        """Fetch and apply config-driven quality filters."""
        markets = await self.fetch_all()
        sc = cfg.scanner
        filtered = [
            m for m in markets
            if m.volume_usd >= sc.min_volume_usd
            and m.liquidity_usd >= sc.min_liquidity_usd
            and (m.days_to_close is None or m.days_to_close <= sc.max_days_to_close)
        ]
        logger.info(
            "scanner.complete",
            platform=self.platform,
            total=len(markets),
            after_filter=len(filtered),
        )
        return filtered
