"""
Bot orchestrator: wires all modules together and runs one full cycle.

Pipeline:
    scanner → filter → research → prediction → risk → execution → learning
"""
from __future__ import annotations

from src.config import cfg
from src.config.rules import load_rules
from src.execution.orderbook import OrderBook
from src.execution.paper import PaperExecutor
from src.filter.market_filter import MarketFilter
from src.learning.tracker import PerformanceTracker, PredRecord
from src.logging_setup import get_logger
from src.prediction.baseline import BaselinePredictor
from src.research.researcher import MarketResearcher
from src.risk.manager import RiskManager
from src.scanner.kalshi import KalshiScanner
from src.scanner.polymarket import PolymarketScanner

logger = get_logger(__name__)


class Bot:
    """Top-level orchestrator. Call `await bot.run_cycle()` each interval."""

    def __init__(self) -> None:
        self.scanner_classes = [PolymarketScanner, KalshiScanner]
        self.rules = load_rules()
        self.market_filter = MarketFilter(rules=self.rules)
        self.researcher = MarketResearcher()
        self.predictor = BaselinePredictor()
        self.tracker = PerformanceTracker()
        # TODO: swap for live executors when TRADING_MODE=live
        self.executor = PaperExecutor()
        self._open_ids: set[str] = set()

    async def run_cycle(self) -> None:
        logger.info("cycle.start", mode=cfg.bot.trading_mode)

        # ── 1. Scan ───────────────────────────────────────────────────────────
        raw_markets = []
        for cls in self.scanner_classes:
            if cfg.platforms.__dict__.get(cls.platform, None) is not None:
                raw_markets.extend(await cls().scan())

        # ── 2. Filter + rank ──────────────────────────────────────────────────
        scored_markets = self.market_filter.run(raw_markets)

        # ── 3–6. Research → Predict → Risk → Execute ─────────────────────────
        risk = RiskManager(open_market_ids=self._open_ids)

        for sm in scored_markets:
            market = sm.market
            research = await self.researcher.research(market)
            pred = await self.predictor.predict(market, research)

            if not pred.has_edge:
                continue

            decision = risk.evaluate(pred)
            if not decision.approved:
                logger.info("cycle.skip", market_id=market.id, reason=decision.reason)
                continue

            # ── Orderbook safety gate ─────────────────────────────────────
            book = OrderBook.from_market(market)
            book_check = book.is_trade_safe(
                pred.recommended_side, decision.size_usd, self.rules,
            )
            if not book_check:
                logger.info(
                    "cycle.skip",
                    market_id=market.id,
                    reason=f"orderbook: {book_check.failures}",
                )
                continue

            price = pred.market_probability if pred.edge > 0 else 1 - pred.market_probability
            trade = await self.executor.submit(
                market_id=market.id,
                platform=market.platform,
                side=pred.recommended_side,
                size_usd=decision.size_usd,
                limit_price=price,
            )
            self._open_ids.add(market.id)

            self.tracker.record(PredRecord(
                market_id=market.id,
                our_probability=pred.our_probability,
                market_probability=pred.market_probability,
                edge=pred.edge,
                side=pred.recommended_side,
                size_usd=decision.size_usd,
                model_name=pred.model_name,
            ))

        logger.info("cycle.end", summary=self.tracker.summary())
