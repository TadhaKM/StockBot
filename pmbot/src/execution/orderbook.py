"""
Order book evaluation: prevents fake edge from bad execution.

Walks the L2 book to estimate realistic fill prices, computes slippage,
and rejects trades where the execution cost would eat the edge.

Usage:
    from src.execution.orderbook import OrderBook

    book = OrderBook(
        bids=[(0.60, 500), (0.59, 300), (0.58, 200)],
        asks=[(0.62, 400), (0.63, 350), (0.64, 100)],
    )
    fill = book.estimate_fill_price("yes", size_usd=600)
    safe = book.is_trade_safe("yes", size_usd=600, rules=rules)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.config.rules import RuleResult, TradingRules
from src.logging_setup import get_logger

logger = get_logger(__name__)

# Type alias: (price, size_usd)
Level = tuple[float, float]


@dataclass
class FillEstimate:
    """Result of walking the book to fill an order."""
    fill_price: float       # volume-weighted average fill price
    slippage: float         # absolute price slippage from best available level
    levels_consumed: int    # number of price levels the order walks through
    fully_filled: bool      # False if the book is too thin to fill the order
    filled_usd: float       # how much was actually fillable


@dataclass
class OrderBook:
    """
    L2 order book for a single market.

    Args:
        bids: list of (price, size_usd) sorted descending by price (best bid first).
        asks: list of (price, size_usd) sorted ascending by price (best ask first).
    """
    bids: list[Level] = field(default_factory=list)
    asks: list[Level] = field(default_factory=list)

    @property
    def best_bid(self) -> float:
        return self.bids[0][0] if self.bids else 0.0

    @property
    def best_ask(self) -> float:
        return self.asks[0][0] if self.asks else 1.0

    @property
    def spread(self) -> float:
        return self.best_ask - self.best_bid

    @property
    def mid_price(self) -> float:
        return (self.best_bid + self.best_ask) / 2

    @property
    def total_bid_depth(self) -> float:
        return sum(size for _, size in self.bids)

    @property
    def total_ask_depth(self) -> float:
        return sum(size for _, size in self.asks)

    def depth_within(self, band: float = 0.02) -> float:
        """
        Total USD resting within `band` of mid_price, both sides combined.
        For prediction markets band is absolute (e.g. 0.02 = 2 cents).
        """
        mid = self.mid_price
        lo = mid - band
        hi = mid + band
        depth = 0.0
        for price, size in self.bids:
            if price >= lo:
                depth += size
        for price, size in self.asks:
            if price <= hi:
                depth += size
        return depth

    def estimate_fill_price(self, side: str, size_usd: float) -> FillEstimate:
        """
        Walk the book to compute the volume-weighted average fill price.

        Args:
            side: "yes" walks the asks (buying YES), "no" walks the bids (selling YES / buying NO).
            size_usd: total USD to fill.
        """
        levels = self.asks if side == "yes" else self.bids
        if not levels:
            return FillEstimate(
                fill_price=0.0,
                slippage=1.0,
                levels_consumed=0,
                fully_filled=False,
                filled_usd=0.0,
            )

        best_price = levels[0][0]
        remaining = size_usd
        cost_sum = 0.0
        filled = 0.0
        consumed = 0

        for price, level_size in levels:
            if remaining <= 0:
                break
            consumed += 1
            take = min(remaining, level_size)
            cost_sum += take * price
            filled += take
            remaining -= take

        fully_filled = remaining <= 0
        vwap = cost_sum / filled if filled > 0 else 0.0

        if side == "yes":
            slippage = vwap - best_price     # paid more than best ask
        else:
            slippage = best_price - vwap     # received less than best bid

        return FillEstimate(
            fill_price=round(vwap, 6),
            slippage=round(max(slippage, 0.0), 6),
            levels_consumed=consumed,
            fully_filled=fully_filled,
            filled_usd=round(filled, 2),
        )

    def is_trade_safe(
        self,
        side: str,
        size_usd: float,
        rules: TradingRules,
    ) -> RuleResult:
        """
        Final execution gate — rejects if slippage or depth is unacceptable.

        Checks:
            1. Depth within 2% of mid >= min_orderbook_depth
            2. Order can be fully filled
            3. Slippage <= max_slippage
        """
        failures: list[str] = []

        # ── Depth check ──
        band = rules.execution.depth_band
        depth = self.depth_within(band)
        if depth < rules.market.min_orderbook_depth:
            failures.append(
                f"depth_near_mid {depth:.0f} USD < min {rules.market.min_orderbook_depth:.0f} USD"
            )

        # ── Fill simulation ──
        fill = self.estimate_fill_price(side, size_usd)

        if not fill.fully_filled:
            failures.append(
                f"book too thin: only {fill.filled_usd:.2f} of {size_usd:.2f} USD fillable"
            )

        if fill.slippage > rules.execution.max_slippage:
            failures.append(
                f"slippage {fill.slippage:.4f} > max {rules.execution.max_slippage:.4f}"
            )

        if failures:
            logger.info(
                "orderbook.rejected",
                side=side,
                size_usd=size_usd,
                fill_price=fill.fill_price,
                slippage=fill.slippage,
                depth_near_mid=depth,
                failures=failures,
            )
            return RuleResult(passed=False, failures=failures)

        logger.info(
            "orderbook.safe",
            side=side,
            size_usd=size_usd,
            fill_price=fill.fill_price,
            slippage=fill.slippage,
            levels=fill.levels_consumed,
        )
        return RuleResult.ok()

    @classmethod
    def from_market(cls, market: "Market", levels: int = 5) -> "OrderBook":
        """
        Build a synthetic book from a Market's top-of-book bid/ask and aggregate depth.

        Distributes orderbook_depth evenly across `levels` price levels,
        spacing each level by half the spread. Useful when only L1 data is available.
        """
        half_spread = market.spread / 2
        step = max(half_spread, 0.005)  # at least half a cent between levels
        depth_per_level = market.orderbook_depth / levels if levels > 0 else 0

        bids = [
            (round(market.bid - i * step, 4), round(depth_per_level, 2))
            for i in range(levels)
        ]
        asks = [
            (round(market.ask + i * step, 4), round(depth_per_level, 2))
            for i in range(levels)
        ]
        return cls(bids=bids, asks=asks)


# Avoid circular import — only used in from_market type hint
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.scanner.base import Market
