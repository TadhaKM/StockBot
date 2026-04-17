"""
Polymarket live executor.

TODO: Implement CLOB order placement.
TODO: Add L1/L2 signing (py-clob-client or raw API).
TODO: Monitor order status via WebSocket.
"""
from __future__ import annotations

from src.logging_setup import get_logger
from .base import BaseExecutor, TradeRecord

logger = get_logger(__name__)


class PolymarketExecutor(BaseExecutor):

    async def submit(self, market_id, platform, side, size_usd, limit_price) -> TradeRecord:
        # TODO: Build CLOB limit order, sign, POST to /order
        raise NotImplementedError("Polymarket live execution not yet implemented")
