"""
Bot orchestrator: wires all modules together and runs one full cycle.

Pipeline:
    scan -> filter -> research -> predict -> risk -> orderbook -> execute

Every step is wrapped so one failure does not kill the cycle. A per-cycle
CycleReport captures counts and step-level errors, and is logged at the end.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.config import cfg
from src.config.rules import load_rules
from src.execution.orderbook import OrderBook
from src.execution.paper import PaperExecutor
from src.filter.market_filter import MarketFilter
from src.learning.tracker import PerformanceTracker, PredRecord
from src.logging_setup import get_logger
from src.prediction.baseline import BaselinePredictor
from src.prediction.engine import PredictionEngine
from src.research.researcher import MarketResearcher
from src.risk.manager import RiskManager
from src.scanner.base import Market
from src.scanner.kalshi import KalshiScanner
from src.scanner.polymarket import PolymarketScanner

logger = get_logger(__name__)


@dataclass
class CycleReport:
    scanned: int = 0
    ranked: int = 0
    signals: int = 0
    risk_passed: int = 0
    book_passed: int = 0
    filled: int = 0
    errors: dict[str, int] = field(default_factory=dict)

    def bump_error(self, step: str) -> None:
        self.errors[step] = self.errors.get(step, 0) + 1

    def as_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "ranked": self.ranked,
            "signals": self.signals,
            "risk_passed": self.risk_passed,
            "book_passed": self.book_passed,
            "filled": self.filled,
            "errors": self.errors,
        }


class Bot:
    """Top-level orchestrator. Call `await bot.run_cycle()` each interval."""

    def __init__(self) -> None:
        self.scanner_classes = [PolymarketScanner, KalshiScanner]
        self.rules = load_rules()
        self.market_filter = MarketFilter(rules=self.rules)
        self.researcher = MarketResearcher()
        self.engine = PredictionEngine(
            predictor=BaselinePredictor(),
            rules=self.rules,
        )
        self.tracker = PerformanceTracker()
        self.executor = PaperExecutor()
        self._open_ids: set[str] = set()

    async def run_cycle(self) -> CycleReport:
        report = CycleReport()
        logger.info("cycle.start", mode=cfg.bot.trading_mode)

        if self.executor.is_halted():
            logger.warning("cycle.halted", reason="STOP file present")
            logger.info("cycle.end", report=report.as_dict(), halted=True)
            return report

        # 1. Scan ─────────────────────────────────────────────────────────────
        raw_markets = await self._safe_scan(report)
        report.scanned = len(raw_markets)
        if not raw_markets:
            logger.warning("cycle.empty_scan")
            logger.info("cycle.end", report=report.as_dict())
            return report

        # 2. Filter ───────────────────────────────────────────────────────────
        try:
            scored = self.market_filter.run(raw_markets)
        except Exception as exc:
            logger.exception("cycle.filter_failed", error=str(exc))
            report.bump_error("filter")
            logger.info("cycle.end", report=report.as_dict())
            return report
        report.ranked = len(scored)
        logger.info("cycle.filtered", scanned=report.scanned, ranked=report.ranked)

        # 3-7. Per-market pipeline ────────────────────────────────────────────
        risk = RiskManager(open_market_ids=self._open_ids)
        for sm in scored:
            try:
                await self._process_market(sm.market, risk, report)
            except Exception as exc:
                logger.exception(
                    "cycle.market_failed",
                    market_id=sm.market.id,
                    error=str(exc),
                )
                report.bump_error("market")

        logger.info(
            "cycle.end",
            report=report.as_dict(),
            paper=self.executor.summary(),
            tracker=self.tracker.summary(),
        )
        return report

    # ── Steps ───────────────────────────────────────────────────────────────

    async def _safe_scan(self, report: CycleReport) -> list[Market]:
        raw: list[Market] = []
        for cls in self.scanner_classes:
            if cfg.platforms.__dict__.get(cls.platform, None) is None:
                continue
            try:
                markets = await cls().scan()
            except Exception as exc:
                logger.exception("scan.failed", platform=cls.platform, error=str(exc))
                report.bump_error(f"scan.{cls.platform}")
                continue
            logger.info("scan.ok", platform=cls.platform, count=len(markets))
            raw.extend(markets)
        return raw

    async def _process_market(
        self,
        market: Market,
        risk: RiskManager,
        report: CycleReport,
    ) -> None:
        # Research
        try:
            research = await self.researcher.research(market)
        except Exception as exc:
            logger.exception("research.failed", market_id=market.id, error=str(exc))
            report.bump_error("research")
            return

        # Predict
        try:
            signal = await self.engine.run(market, research)
        except Exception as exc:
            logger.exception("predict.failed", market_id=market.id, error=str(exc))
            report.bump_error("predict")
            return
        if not signal.is_signal:
            return
        report.signals += 1

        pred = signal.prediction

        # Risk
        try:
            decision = risk.evaluate(pred)
        except Exception as exc:
            logger.exception("risk.failed", market_id=market.id, error=str(exc))
            report.bump_error("risk")
            return
        if not decision.approved:
            logger.info("cycle.skip", market_id=market.id, step="risk", reason=decision.reason)
            return
        report.risk_passed += 1

        # Orderbook gate
        try:
            book = OrderBook.from_market(market)
            book_check = book.is_trade_safe(pred.recommended_side, decision.size_usd, self.rules)
        except Exception as exc:
            logger.exception("orderbook.failed", market_id=market.id, error=str(exc))
            report.bump_error("orderbook")
            return
        if not book_check:
            logger.info(
                "cycle.skip",
                market_id=market.id,
                step="orderbook",
                reason=f"orderbook: {book_check.failures}",
            )
            return
        report.book_passed += 1

        # Execute: limit at our model's fair value -- we'll pay up to what
        # we believe the contract is worth, which is above the current ask
        # by exactly `edge`. Side-native: YES pays p_model, NO pays 1-p_model.
        price = pred.p_model if pred.edge > 0 else 1 - pred.p_model
        try:
            trade = await self.executor.submit(
                market_id=market.id,
                platform=market.platform,
                side=pred.recommended_side,
                size_usd=decision.size_usd,
                limit_price=price,
                book=book,
            )
        except Exception as exc:
            logger.exception("execute.failed", market_id=market.id, error=str(exc))
            report.bump_error("execute")
            return
        if trade is None:
            logger.info("cycle.skip", market_id=market.id, step="execute", reason="paper fill rejected")
            return
        report.filled += 1
        self._open_ids.add(market.id)

        # Record for learning (non-fatal)
        try:
            self.tracker.record(PredRecord(
                market_id=market.id,
                p_model=pred.p_model,
                p_market=pred.p_market,
                edge=pred.edge,
                side=pred.recommended_side,
                size_usd=decision.size_usd,
                model_name=pred.model_name,
            ))
        except Exception as exc:
            logger.exception("tracker.failed", market_id=market.id, error=str(exc))
            report.bump_error("tracker")
