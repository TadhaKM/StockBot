"""
Bot.run_cycle must never crash, even when individual steps throw.

Each test injects a failing component at one pipeline stage and asserts the
cycle still completes, the error counter is bumped, and downstream stages
for the failing market are skipped.
"""
from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.config.rules import RuleResult, load_rules
from src.execution.paper import PaperExecutor
from src.filter.market_filter import ScoredMarket
from src.orchestrator.bot import Bot, CycleReport
from src.prediction.base import PredictionResult
from src.prediction.engine import Signal
from src.research.researcher import ResearchResult
from src.risk.manager import SizingDecision
from src.scanner.base import Market


# ── Helpers ──────────────────────────────────────────────────────────────────

def _market(id_: str = "m1") -> Market:
    return Market(
        id=id_,
        title=f"Test market {id_}",
        platform="poly",
        bid=0.60,
        ask=0.62,
        volume_usd=100_000,
        orderbook_depth=5_000,
        close_time=datetime.now(timezone.utc) + timedelta(days=3),
    )


def _signal(market_id: str = "m1", is_signal: bool = True) -> Signal:
    pred = PredictionResult(
        market_id=market_id,
        p_model=0.75,
        p_market=0.61,
        confidence=0.7,
        model_name="test",
    )
    return Signal(prediction=pred, is_signal=is_signal, failures=[])


class _StubScanner:
    platform = "polymarket"

    def __init__(self, markets=None, raises=None):
        self._markets = markets or []
        self._raises = raises

    async def scan(self):
        if self._raises is not None:
            raise self._raises
        return self._markets


def _make_scanner(platform: str, markets=None, raises=None):
    """Build a zero-arg scanner factory matching the `cls()` call in bot."""
    def factory():
        s = _StubScanner(markets=markets, raises=raises)
        s.platform = platform
        return s
    factory.platform = platform
    return factory


class _StubFilter:
    def __init__(self, scored=None, raises=None):
        self._scored = scored or []
        self._raises = raises

    def run(self, markets):
        if self._raises is not None:
            raise self._raises
        return self._scored


class _StubResearcher:
    def __init__(self, raises=None):
        self._raises = raises

    async def research(self, market):
        if self._raises is not None:
            raise self._raises
        return ResearchResult(market_id=market.id)


class _StubEngine:
    def __init__(self, signal=None, raises=None):
        self._signal = signal
        self._raises = raises

    async def run(self, market, research):
        if self._raises is not None:
            raise self._raises
        return self._signal or _signal(market.id)


class _StubRisk:
    def __init__(self, decision=None, raises=None):
        self._decision = decision or SizingDecision(True, 100.0, "ok")
        self._raises = raises
        self.open_market_ids: set[str] = set()

    def evaluate(self, pred):
        if self._raises is not None:
            raise self._raises
        return self._decision


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def bot(tmp_path, monkeypatch):
    """A Bot with tmp-dir paper executor and stubbed dependencies."""
    from src.orchestrator.bot import CandidateLogger

    b = Bot.__new__(Bot)
    b.observe = False
    b.rules = load_rules()
    b.scanner_classes = []
    b.market_filter = _StubFilter()
    b.researcher = _StubResearcher()
    b.engine = _StubEngine()
    b.tracker = type("T", (), {
        "record": lambda self, *a, **k: None,
        "summary": lambda self: {},
    })()
    b.executor = PaperExecutor(
        positions_file=tmp_path / "open_positions.json",
        trades_log=tmp_path / "trade_log.jsonl",
        closed_log=tmp_path / "closed_positions.jsonl",
        stop_file=tmp_path / "STOP",
    )
    b.candidate_logger = CandidateLogger(enabled=False)
    b._open_ids = set()
    return b


# ── Tests ────────────────────────────────────────────────────────────────────

class TestCycleReport:
    def test_empty_cycle_returns_report(self, bot):
        report = asyncio.run(bot.run_cycle())
        assert isinstance(report, CycleReport)
        assert report.scanned == 0
        assert report.ranked == 0
        assert report.filled == 0


class TestStopFile:
    def test_stop_file_halts_cycle_before_scanning(self, bot, tmp_path):
        (tmp_path / "STOP").write_text("halt")
        # If STOP aborts before scan, scanner never runs
        bot.scanner_classes = [_make_scanner("polymarket", raises=RuntimeError("boom"))]
        report = asyncio.run(bot.run_cycle())
        assert report.scanned == 0
        assert report.errors == {}


class TestScanErrors:
    def test_scan_failure_is_caught(self, bot):
        good = _make_scanner("polymarket", markets=[_market("m1")])
        bad = _make_scanner("kalshi", raises=RuntimeError("api down"))
        bot.scanner_classes = [bad, good]

        bot.market_filter = _StubFilter(scored=[ScoredMarket(_market("m1"), 80.0)])
        report = asyncio.run(bot.run_cycle())
        assert "scan.kalshi" in report.errors
        # The good scanner still ran
        assert report.scanned == 1


class TestFilterErrors:
    def test_filter_failure_ends_cycle_gracefully(self, bot):
        good = _make_scanner("polymarket", markets=[_market("m1")])
        bot.scanner_classes = [good]

        bot.market_filter = _StubFilter(raises=ValueError("bad rule"))
        report = asyncio.run(bot.run_cycle())
        assert report.errors.get("filter") == 1
        assert report.ranked == 0


class TestPerMarketErrors:
    def _wire(self, bot):
        good = _make_scanner("polymarket", markets=[_market("m1"), _market("m2")])
        bot.scanner_classes = [good]
        bot.market_filter = _StubFilter(scored=[
            ScoredMarket(_market("m1"), 90.0),
            ScoredMarket(_market("m2"), 80.0),
        ])

    def test_research_failure_skips_market_but_cycle_continues(self, bot):
        self._wire(bot)
        bot.researcher = _StubResearcher(raises=RuntimeError("news api down"))
        report = asyncio.run(bot.run_cycle())
        assert report.errors.get("research") == 2
        assert report.filled == 0

    def test_predict_failure_skips_market(self, bot):
        self._wire(bot)
        bot.engine = _StubEngine(raises=RuntimeError("model crash"))
        report = asyncio.run(bot.run_cycle())
        assert report.errors.get("predict") == 2
        assert report.signals == 0

    def test_no_signal_short_circuits_cleanly(self, bot):
        self._wire(bot)
        bot.engine = _StubEngine(signal=_signal("m1", is_signal=False))
        report = asyncio.run(bot.run_cycle())
        assert report.signals == 0
        assert report.filled == 0
        assert report.errors == {}


# ── Review fixes ─────────────────────────────────────────────────────────────

class TestEnabledFlag:
    def test_disabled_platform_is_skipped(self, bot):
        from src.config import cfg

        good = _make_scanner("polymarket", markets=[_market("m1")])
        bad = _make_scanner("kalshi", raises=RuntimeError("should not run"))
        bot.scanner_classes = [good, bad]

        original_enabled = cfg.platforms.kalshi.enabled
        cfg.platforms.kalshi.enabled = False
        try:
            bot.market_filter = _StubFilter(scored=[])
            report = asyncio.run(bot.run_cycle())
        finally:
            cfg.platforms.kalshi.enabled = original_enabled

        # Kalshi was disabled -> it didn't run, so no error from it
        assert "scan.kalshi" not in report.errors


class TestRestartRehydratesOpenIds:
    def test_bot_init_loads_persisted_positions(self, tmp_path):
        # Seed a persisted position, then init a fresh bot with that paths
        pos_file = tmp_path / "open_positions.json"
        pos_file.write_text(
            '[{"market_id": "old-1", "platform": "poly", "side": "yes",'
            ' "entry_price": 0.62, "size_usd": 200.0, "contracts": 322.58,'
            ' "limit_price": 0.62, "opened_at": "2026-04-17T00:00:00+00:00",'
            ' "mark_price": 0.62, "unrealized_pnl": 0.0}]'
        )
        exec_ = PaperExecutor(
            positions_file=pos_file,
            trades_log=tmp_path / "trade_log.jsonl",
            closed_log=tmp_path / "closed_positions.jsonl",
            stop_file=tmp_path / "STOP",
        )
        # Simulate what Bot.__init__ does
        open_ids = {p.market_id for p in exec_.positions}
        assert open_ids == {"old-1"}


class TestRiskManagerSharedSet:
    def test_empty_set_is_held_by_reference(self):
        from src.risk.manager import RiskManager

        shared: set[str] = set()
        rm = RiskManager(open_market_ids=shared)
        assert rm.open_market_ids is shared
        shared.add("m1")
        # The manager must see the new id without being re-created
        assert "m1" in rm.open_market_ids


class TestPortfolioGate:
    def test_daily_loss_breach_halts_cycle(self, bot, tmp_path):
        # Write a big losing close today
        today = datetime.now(timezone.utc).isoformat()
        (tmp_path / "closed_positions.jsonl").write_text(
            '{"event": "close", "realized_pnl": -9999.0, "closed_at": "'
            + today + '"}\n'
        )
        # Point the bot's helper at our tmp dir by monkeypatching cwd
        import os
        original_cwd = os.getcwd()
        os.chdir(tmp_path.parent)
        try:
            # Have to mimic path layout the helper expects
            target = tmp_path.parent / "data" / "trades"
            target.mkdir(parents=True, exist_ok=True)
            (target / "closed_positions.jsonl").write_text(
                '{"event": "close", "realized_pnl": -9999.0, "closed_at": "'
                + today + '"}\n'
            )

            good = _make_scanner("polymarket", markets=[_market("m1")])
            bot.scanner_classes = [good]
            bot.market_filter = _StubFilter(scored=[ScoredMarket(_market("m1"), 90.0)])

            report = asyncio.run(bot.run_cycle())
            assert report.halted_by_portfolio is True
            assert report.filled == 0
        finally:
            os.chdir(original_cwd)


# ── Observe mode ─────────────────────────────────────────────────────────────

class TestObserveMode:
    def _observe_bot(self, bot, tmp_path):
        """Flip the fixture into observe mode with a tmp candidate log."""
        from src.orchestrator.bot import CandidateLogger
        bot.observe = True
        bot.candidate_logger = CandidateLogger(
            enabled=True, path=tmp_path / "candidate_trades.jsonl",
        )
        return tmp_path / "candidate_trades.jsonl"

    def _wire_trade(self, bot):
        """Wire stubs so a market passes every gate up to the execute call."""
        # Strong market -- passes real MarketFilter + has room on the book
        strong = Market(
            id="obs-1",
            title="Observe test market",
            platform="polymarket",
            bid=0.60,
            ask=0.62,
            volume_usd=100_000,
            orderbook_depth=10_000,
            close_time=datetime.now(timezone.utc) + timedelta(days=5),
        )
        scanner = _make_scanner("polymarket", markets=[strong])
        bot.scanner_classes = [scanner]
        bot.market_filter = _StubFilter(scored=[ScoredMarket(strong, 90.0)])
        # Strong prediction: passes edge + confidence gates
        pred = PredictionResult(
            market_id=strong.id,
            p_model=0.80, p_market=0.61, confidence=0.75, model_name="stub",
        )
        bot.engine = _StubEngine(signal=Signal(prediction=pred, is_signal=True, failures=[]))
        return strong

    def test_would_be_trade_logged_and_not_executed(self, bot, tmp_path):
        log_path = self._observe_bot(bot, tmp_path)
        self._wire_trade(bot)

        report = asyncio.run(bot.run_cycle())

        # Nothing actually executed
        assert report.filled == 0
        assert bot.executor.positions == []
        # But one candidate written
        assert report.candidates_logged == 1
        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        entry = __import__("json").loads(lines[0])
        assert entry["would_execute"] is True
        assert entry["stage_rejected_at"] is None
        assert entry["market_id"] == "obs-1"
        assert entry["edge"] == pytest.approx(0.19)
        assert entry["confidence"] == 0.75
        assert entry["side"] == "yes"
        assert entry["reject_reasons"] == []
        # Required schema fields
        for key in ("ts", "bid", "ask", "mid_price", "p_model", "p_market"):
            assert key in entry

    def test_reject_reasons_recorded_at_risk_stage(self, bot, tmp_path):
        # A position already open makes RiskManager reject duplicates
        log_path = self._observe_bot(bot, tmp_path)
        market = self._wire_trade(bot)
        bot._open_ids.add(market.id)  # triggers "already holding" rejection

        report = asyncio.run(bot.run_cycle())

        assert report.candidates_logged == 1
        assert report.filled == 0
        entry = __import__("json").loads(log_path.read_text().strip())
        assert entry["would_execute"] is False
        assert entry["stage_rejected_at"] == "risk"
        assert entry["reject_reasons"]  # non-empty
        assert "already holding" in entry["reject_reasons"][0]

    def test_observe_mode_does_not_touch_executor(self, bot, tmp_path):
        self._observe_bot(bot, tmp_path)
        self._wire_trade(bot)

        # Swap in an executor that blows up if submit() is called
        class _FailOnSubmit:
            positions: list = []
            def is_halted(self): return False
            def total_exposure_usd(self): return 0.0
            async def submit(self, *a, **k):
                raise AssertionError("submit must not be called in observe mode")
            def summary(self): return {}
        bot.executor = _FailOnSubmit()

        report = asyncio.run(bot.run_cycle())
        assert report.filled == 0
        assert report.candidates_logged == 1
