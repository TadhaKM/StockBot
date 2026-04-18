"""
Paper trading engine.

Limit orders only -- submissions are rejected if the book can't fill
at or better than the requested price. Every filled order opens a
Position that is persisted to data/trades/open_positions.json and can
be marked-to-market on demand. A STOP file (data/STOP) halts all new
submissions.

Files written:
    data/trades/open_positions.json    -- live positions (overwritten)
    data/trades/trades.jsonl           -- every trade event (appended)
    data/trades/closed_positions.jsonl -- realised closures (appended)

Kill switch:
    Create data/STOP to halt all new submissions. Delete to resume.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.execution.orderbook import OrderBook
from src.logging_setup import get_logger
from .base import BaseExecutor, TradeRecord

logger = get_logger(__name__)

_TRADES_DIR = Path("data/trades")
_POSITIONS_FILE = _TRADES_DIR / "open_positions.json"
_TRADES_LOG = _TRADES_DIR / "trade_log.jsonl"
_CLOSED_LOG = _TRADES_DIR / "closed_positions.jsonl"
_STOP_FILE = Path("data/STOP")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Position ─────────────────────────────────────────────────────────────────

@dataclass
class Position:
    """
    One open paper position.

    Prices are side-native: for a YES position, entry_price is the YES contract
    price paid (0-1). For a NO position, entry_price is the NO contract price
    paid (also 0-1, equal to 1 minus the YES price sold).

    PnL logic is the same in either case:
        unrealized_pnl = (mark_price - entry_price) * contracts
    """
    market_id: str
    platform: str
    side: str             # "yes" or "no"
    entry_price: float    # side-native
    size_usd: float
    contracts: float
    limit_price: float    # the submitted limit
    opened_at: str
    mark_price: float = 0.0
    unrealized_pnl: float = 0.0

    def update_mark(self, side_native_price: float) -> None:
        self.mark_price = round(side_native_price, 6)
        self.unrealized_pnl = round(
            (self.mark_price - self.entry_price) * self.contracts, 4
        )

    @property
    def unrealized_pnl_pct(self) -> float:
        return self.unrealized_pnl / self.size_usd if self.size_usd > 0 else 0.0


# ── Fill simulation ──────────────────────────────────────────────────────────

@dataclass
class _LimitFill:
    vwap_side: float      # side-native VWAP (the price we paid)
    filled_usd: float     # how much was filled (USD)
    contracts: float      # contracts acquired
    fully_filled: bool


def _simulate_limit_fill(
    book: OrderBook, side: str, size_usd: float, limit_price: float,
) -> _LimitFill | None:
    """
    Walk the book taking only levels that satisfy the limit.
    Returns None if no part of the order fills.

    For "yes": walk asks, accept only ask <= limit_price.
    For "no":  walk bids, accept only bid >= (1 - limit_price).
    """
    if side == "yes":
        levels = [(p, sz) for p, sz in book.asks if p <= limit_price]
    elif side == "no":
        threshold = 1.0 - limit_price
        levels = [(p, sz) for p, sz in book.bids if p >= threshold]
    else:
        raise ValueError(f"side must be 'yes' or 'no', got {side!r}")

    if not levels:
        return None

    remaining = size_usd
    cost_sum = 0.0
    filled_usd = 0.0
    for price, level_sz in levels:
        if remaining <= 0:
            break
        take = min(remaining, level_sz)
        effective = price if side == "yes" else 1.0 - price
        cost_sum += take * effective
        filled_usd += take
        remaining -= take

    if filled_usd == 0:
        return None

    vwap_side = cost_sum / filled_usd
    contracts = filled_usd / vwap_side if vwap_side > 0 else 0.0

    return _LimitFill(
        vwap_side=round(vwap_side, 6),
        filled_usd=round(filled_usd, 2),
        contracts=round(contracts, 4),
        fully_filled=remaining <= 0,
    )


# ── Engine ───────────────────────────────────────────────────────────────────

class PaperExecutor(BaseExecutor):
    """
    Limit-order paper trading engine.

    Call:
        await exec.submit(market_id, platform, side, size_usd, limit_price, book)
            -> TradeRecord if filled, None if rejected.
        exec.mark_to_market({market_id: yes_price, ...})
        exec.close_position(market_id, yes_price) -> realized PnL
    """

    def __init__(
        self,
        positions_file: Path = _POSITIONS_FILE,
        trades_log: Path = _TRADES_LOG,
        closed_log: Path = _CLOSED_LOG,
        stop_file: Path = _STOP_FILE,
    ) -> None:
        self._positions_file = positions_file
        self._trades_log = trades_log
        self._closed_log = closed_log
        self._stop_file = stop_file

        self._positions_file.parent.mkdir(parents=True, exist_ok=True)
        self._stop_file.parent.mkdir(parents=True, exist_ok=True)

        self._positions: dict[str, Position] = self._load_positions()

    # ── Persistence ─────────────────────────────────────────────────────────

    def _load_positions(self) -> dict[str, Position]:
        if not self._positions_file.exists():
            return {}
        try:
            data = json.loads(self._positions_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("paper.positions_unreadable", file=str(self._positions_file))
            return {}
        return {d["market_id"]: Position(**d) for d in data}

    def _persist_positions(self) -> None:
        data = [asdict(p) for p in self._positions.values()]
        self._positions_file.write_text(
            json.dumps(data, indent=2), encoding="utf-8",
        )

    def _append_trade(self, record: dict, path: Path) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    # ── Kill switch ─────────────────────────────────────────────────────────

    def is_halted(self) -> bool:
        return self._stop_file.exists()

    # ── Submit ──────────────────────────────────────────────────────────────

    async def submit(
        self,
        market_id: str,
        platform: str,
        side: str,
        size_usd: float,
        limit_price: float,
        book: OrderBook | None = None,
    ) -> TradeRecord | None:
        """
        Submit a limit order. Returns TradeRecord if (fully) filled, else None.

        Rejection causes (all logged):
          - STOP file present
          - no book provided (we need one to simulate a fill)
          - book can't fill any portion at the requested limit
          - already holding a position in this market
        """
        if self.is_halted():
            logger.warning("paper.halted", market_id=market_id, reason="STOP file present")
            return None

        if market_id in self._positions:
            logger.info("paper.duplicate", market_id=market_id)
            return None

        if book is None:
            logger.info("paper.no_book", market_id=market_id)
            return None

        fill = _simulate_limit_fill(book, side, size_usd, limit_price)
        if fill is None or fill.filled_usd <= 0:
            logger.info(
                "paper.rejected",
                market_id=market_id,
                side=side,
                size_usd=size_usd,
                limit_price=limit_price,
                reason="book can't fill at limit",
            )
            return None

        # Create position
        pos = Position(
            market_id=market_id,
            platform=platform,
            side=side,
            entry_price=fill.vwap_side,
            size_usd=fill.filled_usd,
            contracts=fill.contracts,
            limit_price=limit_price,
            opened_at=_now(),
            mark_price=fill.vwap_side,     # initially mark == entry
            unrealized_pnl=0.0,
        )
        self._positions[market_id] = pos
        self._persist_positions()

        # Write trade record
        record = TradeRecord(
            trade_id=str(uuid.uuid4()),
            market_id=market_id,
            platform=platform,
            side=side,
            contracts=pos.contracts,
            fill_price=pos.entry_price,
            size_usd=pos.size_usd,
            paper=True,
            filled_at=pos.opened_at,
        )
        self._append_trade({"event": "open", **asdict(record),
                            "limit_price": limit_price,
                            "fully_filled": fill.fully_filled}, self._trades_log)

        logger.info(
            "paper.filled",
            market_id=market_id,
            side=side,
            entry_price=pos.entry_price,
            contracts=pos.contracts,
            size_usd=pos.size_usd,
            fully_filled=fill.fully_filled,
        )
        return record

    # ── Mark-to-market ──────────────────────────────────────────────────────

    def mark_to_market(self, yes_prices: dict[str, float]) -> None:
        """
        Update unrealized PnL for every open position whose market_id appears
        in `yes_prices`. For NO positions we invert the YES price automatically.
        """
        for market_id, yes_price in yes_prices.items():
            pos = self._positions.get(market_id)
            if pos is None:
                continue
            side_price = yes_price if pos.side == "yes" else 1.0 - yes_price
            pos.update_mark(side_price)
        self._persist_positions()

    # ── Close ───────────────────────────────────────────────────────────────

    def close_position(self, market_id: str, yes_price: float) -> float | None:
        """
        Close a position at the given YES market price. Returns realized PnL (USD)
        or None if no such position.
        """
        pos = self._positions.pop(market_id, None)
        if pos is None:
            return None

        exit_side_price = yes_price if pos.side == "yes" else 1.0 - yes_price
        realized = round((exit_side_price - pos.entry_price) * pos.contracts, 4)

        self._persist_positions()
        self._append_trade(
            {
                "event": "close",
                "market_id": pos.market_id,
                "platform": pos.platform,
                "side": pos.side,
                "entry_price": pos.entry_price,
                "exit_price": round(exit_side_price, 6),
                "contracts": pos.contracts,
                "size_usd": pos.size_usd,
                "realized_pnl": realized,
                "closed_at": _now(),
            },
            self._closed_log,
        )
        self._append_trade(
            {
                "event": "close",
                "market_id": pos.market_id,
                "realized_pnl": realized,
                "closed_at": _now(),
            },
            self._trades_log,
        )

        logger.info(
            "paper.closed",
            market_id=market_id,
            side=pos.side,
            entry=pos.entry_price,
            exit=round(exit_side_price, 6),
            realized_pnl=realized,
        )
        return realized

    # ── Inspection ──────────────────────────────────────────────────────────

    @property
    def positions(self) -> list[Position]:
        return list(self._positions.values())

    def total_exposure_usd(self) -> float:
        return round(sum(p.size_usd for p in self._positions.values()), 2)

    def total_unrealized_pnl(self) -> float:
        return round(sum(p.unrealized_pnl for p in self._positions.values()), 4)

    def summary(self) -> dict:
        return {
            "open_positions": len(self._positions),
            "total_exposure_usd": self.total_exposure_usd(),
            "total_unrealized_pnl": self.total_unrealized_pnl(),
            "halted": self.is_halted(),
        }
