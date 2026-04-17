"""
Kalshi live executor.

TODO: Implement order submission using Kalshi REST API v2.
"""
from __future__ import annotations

from src.models import Order, Trade
from src.utils import get_logger
from .base import BaseExecutor

logger = get_logger(__name__)


class KalshiExecutor(BaseExecutor):

    async def submit(self, order: Order) -> Trade:
        # TODO: POST /portfolio/orders
        # TODO: Handle RESTING vs IMMEDIATE_OR_CANCEL order types
        # TODO: Monitor order status via WebSocket feed
        raise NotImplementedError("Kalshi live execution not yet implemented")

    async def cancel(self, order_id: str) -> bool:
        # TODO: DELETE /portfolio/orders/{order_id}
        raise NotImplementedError

    async def get_open_orders(self) -> list[Order]:
        # TODO: GET /portfolio/orders?status=resting
        raise NotImplementedError
