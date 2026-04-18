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
    b = Bot.__new__(Bot)
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
