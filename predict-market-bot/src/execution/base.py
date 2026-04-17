"""Abstract executor interface."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.models import Order, Trade


class BaseExecutor(ABC):

    @abstractmethod
    async def submit(self, order: Order) -> Trade:
        """Submit an order and return the resulting trade."""
        ...

    @abstractmethod
    async def cancel(self, order_id: str) -> bool:
        """Cancel a pending order. Returns True if successful."""
        ...

    @abstractmethod
    async def get_open_orders(self) -> list[Order]:
        """Return all open orders."""
        ...
