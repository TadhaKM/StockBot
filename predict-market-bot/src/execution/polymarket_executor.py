"""
Polymarket live executor.

TODO: Implement full CLOB order placement using the py-clob-client library
      or direct API calls with L1/L2 authentication.
"""
from __future__ import annotations

from src.models import Order, Trade
from src.utils import get_logger
from .base import BaseExecutor

logger = get_logger(__name__)


class PolymarketExecutor(BaseExecutor):

    async def submit(self, order: Order) -> Trade:
        # TODO: Build and sign a CLOB order
        # TODO: POST to /order endpoint
        # TODO: Handle partial fills, queue monitoring
        raise NotImplementedError("Polymarket live execution not yet implemented")

    async def cancel(self, order_id: str) -> bool:
        # TODO: DELETE /order/{order_id}
        raise NotImplementedError

    async def get_open_orders(self) -> list[Order]:
        # TODO: GET /orders?status=open
        raise NotImplementedError
