"""
Kalshi live executor.

TODO: Implement order placement via Kalshi REST API v2.
TODO: Add HMAC-SHA256 authentication.
TODO: Handle RESTING vs IOC order types.
"""
from __future__ import annotations

from src.logging_setup import get_logger
from .base import BaseExecutor, TradeRecord

logger = get_logger(__name__)


class KalshiExecutor(BaseExecutor):

    async def submit(self, market_id, platform, side, size_usd, limit_price) -> TradeRecord:
        # TODO: POST /portfolio/orders
        raise NotImplementedError("Kalshi live execution not yet implemented")
