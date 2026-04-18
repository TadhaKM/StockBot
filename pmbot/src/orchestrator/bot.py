"""
Bot orchestrator: wires all modules together and runs one full cycle.

Pipeline:
    scan -> filter -> research -> predict -> risk -> orderbook -> execute

Every step is wrapped so one failure does not kill the cycle. A per-cycle
CycleReport captures counts and step-level errors, and is logged at the end.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import json
from datetime import datetime, timezone
from pathlib import Path

from src.config import cfg
from src.config.rules import BotState, load_rules, validate_trade_allowed
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


_CANDIDATE_LOG = Path("data/logs/candidate_trades.jsonl")


@dataclass
class CycleReport:
    scanned: int = 0
    ranked: int = 0
    signals: int = 0
    risk_passed: int = 0
    portfolio_passed: int = 0
    book_passed: int = 0
    filled: int = 0
    candidates_logged: int = 0
    halted_by_portfolio: bool = False
    errors: dict[str, int] = field(default_factory=dict)

    def bump_error(self, step: str) -> None:
        self.errors[step] = self.errors.get(step, 0) + 1

    def as_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "ranked": self.ranked,
            "signals": self.signals,
            "risk_passed": self.risk_passed,
            "portfolio_passed": self.portfolio_passed,
            "book_passed": self.book_passed,
            "filled": self.filled,
            "candidates_logged": self.candidates_logged,
            "halted_by_portfolio": self.halted_by_portfolio,
            "errors": self.errors,
        }


class CandidateLogger:
    """
    Writes candidate-trade records to data/logs/candidate_trades.jsonl.

    A candidate is any signal-producing market -- regardless of whether it
    ultimately passed every gate. The record carries the stage it was
    rejected at (if any) so you can reconstruct every decision the bot
    would have made in paper mode.

    In non-observe mode the logger is a no-op.
    """

    def __init__(self, enabled: bool, path: Path = _CANDIDATE_LOG) -> None:
        self.enabled = enabled
        self.path = path
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        *,
        market: Market,
        pred,
        decision=None,
        stage_rejected_at: str | None = None,
        reject_reasons: list[str] | None = None,
        would_execute: bool = False,
    ) -> None:
        if not self.enabled:
            return
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "market_id": market.id,
            "platform": market.platform,
            "title": market.title,
            "bid": market.bid,
            "ask": market.ask,
            "mid_price": round(market.mid_price, 6),
            "p_model": round(pred.p_model, 6),
            "p_market": round(pred.p_market, 6),
            "edge": round(pred.edge, 6),
            "confidence": round(pred.confidence, 4),
            "side": pred.recommended_side,
            "size_usd": round(decision.size_usd, 2) if decision is not None else None,
            "stage_rejected_at": stage_rejected_at,
            "would_execute": would_execute,
            "reject_reasons": reject_reasons or [],
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


class Bot:
    """Top-level orchestrator. Call `await bot.run_cycle()` each interval."""

    def __init__(self, observe: bool = False) -> None:
        self.observe = observe
        self.scanner_classes = [PolymarketScanner, KalshiScanner]
        self.rules = load_rules()
        self.market_filter = MarketFilter(rules=self.rules)
        self.researcher = MarketResearcher()
        self.engine = PredictionEngine(
            predictor=BaselinePredictor(),
            rules=self.rules,
        )
        self.tracker = PerformanceTracker()
        self.candidate_logger = CandidateLogger(enabled=observe)

        if cfg.bot.trading_mode == "live":
            logger.warning(
                "bot.live_mode_not_implemented",
                falling_back_to="paper",
                note="live executor not implemented; using PaperExecutor",
            )
        self.executor = PaperExecutor()
        if observe:
            logger.info("bot.observe_mode", note="no trades will be executed",
                        log=str(_CANDIDATE_LOG))

        # Re-hydrate the open-id set from whatever positions the paper
        # engine restored from disk, so duplicate / max-position checks
        # are correct on restart.
        self._open_ids: set[str] = {p.market_id for p in self.executor.positions}
        if self._open_ids:
            logger.info("bot.loaded_positions", count=len(self._open_ids))

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

        # 3. Portfolio-wide risk gate (once per cycle) ────────────────────────
        portfolio_state = self._snapshot_state()
        portfolio_check = validate_trade_allowed(portfolio_state, self.rules)
        if not portfolio_check.passed:
            logger.warning(
                "cycle.portfolio_halt",
                failures=portfolio_check.failures,
                state={
                    "open_positions": portfolio_state.open_positions,
                    "total_exposure_fraction": round(portfolio_state.total_exposure_fraction, 4),
                    "daily_loss_fraction": round(portfolio_state.daily_loss_fraction, 4),
                    "drawdown_fraction": round(portfolio_state.drawdown_fraction, 4),
                },
            )
            report.halted_by_portfolio = True
            logger.info("cycle.end", report=report.as_dict(), paper=self.executor.summary())
            return report

        # 4-7. Per-market pipeline ────────────────────────────────────────────
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

    # ── Candidate logging (observe mode only) ──────────────────────────────

    def _log_candidate(self, market, pred, **kwargs) -> None:
        """Forward to CandidateLogger -- safe to call always, no-op off mode."""
        try:
            self.candidate_logger.write(market=market, pred=pred, **kwargs)
        except Exception as exc:
            logger.warning("candidate.log_failed", market_id=market.id, error=str(exc))

    # ── Portfolio snapshot ──────────────────────────────────────────────────

    def _snapshot_state(self) -> BotState:
        """Build a BotState from the paper executor + closed-position history."""
        bankroll = max(cfg.risk.bankroll_usd, 1e-9)
        exposure = self.executor.total_exposure_usd() / bankroll
        daily_loss, drawdown = self._read_closed_pnl(bankroll)
        return BotState(
            open_positions=len(self.executor.positions),
            total_exposure_fraction=exposure,
            daily_loss_fraction=daily_loss,
            drawdown_fraction=drawdown,
        )

    @staticmethod
    def _read_closed_pnl(bankroll: float) -> tuple[float, float]:
        """
        Scan closed_positions.jsonl to derive (daily_loss_frac, drawdown_frac).

        daily_loss_frac: today's realized loss / bankroll (positive = losing)
        drawdown_frac:   peak-to-trough dip in cumulative realised PnL / bankroll
        """
        path = Path("data/trades/closed_positions.jsonl")
        if not path.exists():
            return 0.0, 0.0

        today = datetime.now(timezone.utc).date().isoformat()
        today_pnl = 0.0
        cum = 0.0
        peak = 0.0
        worst_drawdown = 0.0

        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                pnl = float(entry.get("realized_pnl", 0.0))
                closed_at = entry.get("closed_at", "")
                if closed_at.startswith(today):
                    today_pnl += pnl
                cum += pnl
                peak = max(peak, cum)
                worst_drawdown = max(worst_drawdown, peak - cum)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("bot.closed_pnl_unreadable", error=str(exc))
            return 0.0, 0.0

        daily_loss_frac = max(-today_pnl, 0.0) / bankroll
        drawdown_frac = worst_drawdown / bankroll
        return daily_loss_frac, drawdown_frac

    # ── Steps ───────────────────────────────────────────────────────────────

    async def _safe_scan(self, report: CycleReport) -> list[Market]:
        raw: list[Market] = []
        for cls in self.scanner_classes:
            platform_cfg = getattr(cfg.platforms, cls.platform, None)
            if platform_cfg is None:
                logger.info("scan.skipped", platform=cls.platform, reason="no_config")
                continue
            if not platform_cfg.enabled:
                logger.info("scan.skipped", platform=cls.platform, reason="disabled")
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
            self._log_candidate(
                market, pred, decision=None,
                stage_rejected_at="risk",
                reject_reasons=[decision.reason],
            )
            report.candidates_logged += 1
            return
        report.risk_passed += 1

        # Portfolio exposure after this hypothetical fill
        bankroll = cfg.risk.bankroll_usd
        projected_exposure = (self.executor.total_exposure_usd() + decision.size_usd) / bankroll
        max_exposure = self.rules.sizing.max_total_exposure
        if projected_exposure > max_exposure:
            reason = f"projected exposure {projected_exposure:.2%} > max {max_exposure:.2%}"
            logger.info("cycle.skip", market_id=market.id, step="portfolio", reason=reason)
            self._log_candidate(
                market, pred, decision=decision,
                stage_rejected_at="portfolio",
                reject_reasons=[reason],
            )
            report.candidates_logged += 1
            return
        report.portfolio_passed += 1

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
            self._log_candidate(
                market, pred, decision=decision,
                stage_rejected_at="orderbook",
                reject_reasons=list(book_check.failures),
            )
            report.candidates_logged += 1
            return
        report.book_passed += 1

        # In observe mode we stop here -- no executor call, no open-id update.
        # The candidate is logged as a would-be trade for later review.
        if self.observe:
            self._log_candidate(
                market, pred, decision=decision,
                stage_rejected_at=None,
                reject_reasons=[],
                would_execute=True,
            )
            report.candidates_logged += 1
            logger.info(
                "cycle.observe",
                market_id=market.id,
                edge=round(pred.edge, 4),
                confidence=pred.confidence,
                side=pred.recommended_side,
                size_usd=decision.size_usd,
            )
            return

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
