"""Abstract base class for market scanners."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.models import Market
from src.utils import get_logger

logger = get_logger(__name__)


class BaseScanner(ABC):
    """Fetches and filters markets from a prediction platform."""

    platform_name: str = "unknown"

    @abstractmethod
    async def fetch_markets(self) -> list[Market]:
        """Return all active markets from the platform."""
        ...

    async def scan(
        self,
        min_volume: float = 1_000,
        min_liquidity: float = 500,
        max_days_to_close: float = 90,
    ) -> list[Market]:
        """
        Fetch markets and apply basic quality filters.

        Args:
            min_volume: Minimum lifetime volume in USD.
            min_liquidity: Minimum current liquidity in USD.
            max_days_to_close: Ignore markets closing too far out.
        """
        markets = await self.fetch_markets()
        logger.info("scanner.fetched", platform=self.platform_name, count=len(markets))

        filtered = [
            m for m in markets
            if m.volume_usd >= min_volume
            and m.liquidity_usd >= min_liquidity
            and (m.days_to_close is None or m.days_to_close <= max_days_to_close)
        ]
        logger.info(
            "scanner.filtered",
            platform=self.platform_name,
            before=len(markets),
            after=len(filtered),
        )
        return filtered
