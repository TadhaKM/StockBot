"""
Paper trading executor.

Simulates immediate fills at the limit price. All trades are written to
data/paper_trades/ as newline-delimited JSON for later review.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from src.models import Order, OrderStatus, Trade
from src.utils import get_logger
from .base import BaseExecutor

logger = get_logger(__name__)

_PAPER_TRADES_DIR = Path("data/paper_trades")


class PaperExecutor(BaseExecutor):
    """Simulated executor — no real money moves."""

    def __init__(self) -> None:
        _PAPER_TRADES_DIR.mkdir(parents=True, exist_ok=True)
        self._open_orders: dict[str, Order] = {}

    async def submit(self, order: Order) -> Trade:
        # Simulate immediate fill at limit price
        order.id = order.id or str(uuid.uuid4())
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.utcnow()
        order.fill_price = order.limit_price
        order.paper = True

        trade = Trade(order=order)
        self._persist(trade)

        logger.info(
            "paper.filled",
            order_id=order.id,
            market_id=order.market_id,
            outcome=order.outcome,
            contracts=order.contracts,
            price=order.fill_price,
        )
        return trade

    async def cancel(self, order_id: str) -> bool:
        if order_id in self._open_orders:
            self._open_orders[order_id].status = OrderStatus.CANCELLED
            del self._open_orders[order_id]
            return True
        return False

    async def get_open_orders(self) -> list[Order]:
        return list(self._open_orders.values())

    def _persist(self, trade: Trade) -> None:
        path = _PAPER_TRADES_DIR / f"{datetime.utcnow().date()}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(trade.model_dump_json() + "\n")
