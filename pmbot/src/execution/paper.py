"""Paper executor — immediate fill at limit price, persisted to data/trades/."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from src.logging_setup import get_logger
from .base import BaseExecutor, TradeRecord

logger = get_logger(__name__)
_TRADES_DIR = Path("data/trades")


class PaperExecutor(BaseExecutor):

    def __init__(self) -> None:
        _TRADES_DIR.mkdir(parents=True, exist_ok=True)

    async def submit(
        self,
        market_id: str,
        platform: str,
        side: str,
        size_usd: float,
        limit_price: float,
    ) -> TradeRecord:
        contracts = round(size_usd / limit_price, 4) if limit_price > 0 else 0
        record = TradeRecord(
            trade_id=str(uuid.uuid4()),
            market_id=market_id,
            platform=platform,
            side=side,
            contracts=contracts,
            fill_price=limit_price,
            size_usd=size_usd,
            paper=True,
        )
        self._persist(record)
        logger.info(
            "paper.filled",
            market_id=market_id,
            side=side,
            contracts=contracts,
            price=limit_price,
            size_usd=size_usd,
        )
        return record

    @staticmethod
    def _persist(record: TradeRecord) -> None:
        from datetime import date
        path = _TRADES_DIR / f"{date.today().isoformat()}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.__dict__) + "\n")
