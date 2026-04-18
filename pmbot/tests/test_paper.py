"""Tests for the paper trading engine."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.execution.orderbook import OrderBook
from src.execution.paper import PaperExecutor, Position, _simulate_limit_fill


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_exec(tmp_path: Path) -> PaperExecutor:
    """A fresh executor whose files are all inside a tmp dir."""
    return PaperExecutor(
        positions_file=tmp_path / "open_positions.json",
        trades_log=tmp_path / "trade_log.jsonl",
        closed_log=tmp_path / "closed_positions.jsonl",
        stop_file=tmp_path / "STOP",
    )


def _book() -> OrderBook:
    """Standard book with tight spread and decent depth."""
    return OrderBook(
        bids=[(0.60, 500), (0.59, 300), (0.58, 200)],
        asks=[(0.62, 400), (0.63, 350), (0.64, 100)],
    )


# ── Limit fill simulation ────────────────────────────────────────────────────

class TestSimulateLimitFill:
    def test_yes_fills_at_top_when_limit_above_ask(self):
        fill = _simulate_limit_fill(_book(), "yes", size_usd=200, limit_price=0.62)
        assert fill is not None
        assert fill.vwap_side == pytest.approx(0.62)
        assert fill.fully_filled is True
        assert fill.filled_usd == pytest.approx(200.0)

    def test_yes_rejects_when_limit_below_best_ask(self):
        # Best ask is 0.62; limit of 0.61 can't fill
        fill = _simulate_limit_fill(_book(), "yes", size_usd=200, limit_price=0.61)
        assert fill is None

    def test_yes_partial_fill_walks_only_within_limit(self):
        # limit=0.62 allows first level (400 USD), not deeper
        fill = _simulate_limit_fill(_book(), "yes", size_usd=1000, limit_price=0.62)
        assert fill is not None
        assert fill.fully_filled is False
        assert fill.filled_usd == pytest.approx(400.0)
        assert fill.vwap_side == pytest.approx(0.62)

    def test_yes_walks_two_levels(self):
        # limit=0.63 allows 400 at 0.62 + 350 at 0.63 = 750
        fill = _simulate_limit_fill(_book(), "yes", size_usd=750, limit_price=0.63)
        assert fill is not None
        assert fill.fully_filled is True
        expected_vwap = (400 * 0.62 + 350 * 0.63) / 750
        assert fill.vwap_side == pytest.approx(expected_vwap, abs=1e-4)

    def test_no_fills_when_bid_high_enough(self):
        # Buying NO at limit 0.40 means selling YES at >= 0.60. Best bid is 0.60.
        fill = _simulate_limit_fill(_book(), "no", size_usd=200, limit_price=0.40)
        assert fill is not None
        # NO price paid = 1 - 0.60 = 0.40
        assert fill.vwap_side == pytest.approx(0.40)

    def test_no_rejects_when_bid_too_low(self):
        # Limit NO=0.38 requires YES bid >= 0.62, but best bid is 0.60
        fill = _simulate_limit_fill(_book(), "no", size_usd=200, limit_price=0.38)
        assert fill is None

    def test_bad_side_raises(self):
        with pytest.raises(ValueError):
            _simulate_limit_fill(_book(), "maybe", size_usd=100, limit_price=0.50)

    def test_contracts_equals_size_over_price(self):
        fill = _simulate_limit_fill(_book(), "yes", size_usd=124, limit_price=0.62)
        assert fill is not None
        # contracts should be 124 / 0.62 = 200
        assert fill.contracts == pytest.approx(200.0, abs=0.01)


# ── Submit ────────────────────────────────────────────────────────────────────

class TestSubmit:
    def test_successful_submission(self, tmp_exec):
        rec = asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="yes",
            size_usd=200, limit_price=0.62, book=_book(),
        ))
        assert rec is not None
        assert rec.market_id == "m1"
        assert rec.fill_price == pytest.approx(0.62)
        assert rec.paper is True
        assert len(tmp_exec.positions) == 1

    def test_rejected_when_limit_too_tight(self, tmp_exec):
        rec = asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="yes",
            size_usd=200, limit_price=0.50, book=_book(),
        ))
        assert rec is None
        assert len(tmp_exec.positions) == 0

    def test_rejected_without_book(self, tmp_exec):
        rec = asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="yes",
            size_usd=200, limit_price=0.62, book=None,
        ))
        assert rec is None

    def test_duplicate_market_rejected(self, tmp_exec):
        asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="yes",
            size_usd=200, limit_price=0.62, book=_book(),
        ))
        second = asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="yes",
            size_usd=100, limit_price=0.62, book=_book(),
        ))
        assert second is None
        assert len(tmp_exec.positions) == 1

    def test_partial_fill_still_opens_position(self, tmp_exec):
        # 1000 USD requested, only 400 fillable at limit 0.62
        rec = asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="yes",
            size_usd=1000, limit_price=0.62, book=_book(),
        ))
        assert rec is not None
        assert rec.size_usd == pytest.approx(400.0)

    def test_position_fields_populated(self, tmp_exec):
        asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="yes",
            size_usd=200, limit_price=0.62, book=_book(),
        ))
        pos = tmp_exec.positions[0]
        assert pos.market_id == "m1"
        assert pos.side == "yes"
        assert pos.entry_price == pytest.approx(0.62)
        assert pos.contracts == pytest.approx(200 / 0.62, abs=0.01)
        assert pos.unrealized_pnl == 0.0      # mark == entry on open
        assert pos.mark_price == pytest.approx(0.62)


# ── Kill switch ───────────────────────────────────────────────────────────────

class TestKillSwitch:
    def test_not_halted_by_default(self, tmp_exec):
        assert tmp_exec.is_halted() is False

    def test_stop_file_halts_submissions(self, tmp_exec, tmp_path):
        (tmp_path / "STOP").write_text("halt")
        rec = asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="yes",
            size_usd=200, limit_price=0.62, book=_book(),
        ))
        assert rec is None
        assert tmp_exec.is_halted() is True

    def test_removing_stop_file_resumes(self, tmp_exec, tmp_path):
        stop = tmp_path / "STOP"
        stop.write_text("halt")
        assert tmp_exec.is_halted() is True
        stop.unlink()
        assert tmp_exec.is_halted() is False
        rec = asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="yes",
            size_usd=200, limit_price=0.62, book=_book(),
        ))
        assert rec is not None


# ── Persistence ───────────────────────────────────────────────────────────────

class TestPersistence:
    def test_positions_written_to_json(self, tmp_exec, tmp_path):
        asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="yes",
            size_usd=200, limit_price=0.62, book=_book(),
        ))
        data = json.loads((tmp_path / "open_positions.json").read_text())
        assert len(data) == 1
        assert data[0]["market_id"] == "m1"

    def test_positions_reload_on_new_instance(self, tmp_path):
        e1 = PaperExecutor(
            positions_file=tmp_path / "open_positions.json",
            trades_log=tmp_path / "trade_log.jsonl",
            closed_log=tmp_path / "closed_positions.jsonl",
            stop_file=tmp_path / "STOP",
        )
        asyncio.run(e1.submit(
            market_id="m1", platform="poly", side="yes",
            size_usd=200, limit_price=0.62, book=_book(),
        ))

        e2 = PaperExecutor(
            positions_file=tmp_path / "open_positions.json",
            trades_log=tmp_path / "trade_log.jsonl",
            closed_log=tmp_path / "closed_positions.jsonl",
            stop_file=tmp_path / "STOP",
        )
        assert len(e2.positions) == 1
        assert e2.positions[0].market_id == "m1"

    def test_trades_jsonl_appended(self, tmp_exec, tmp_path):
        asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="yes",
            size_usd=200, limit_price=0.62, book=_book(),
        ))
        lines = (tmp_path / "trade_log.jsonl").read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event"] == "open"
        assert record["market_id"] == "m1"


# ── Mark-to-market ───────────────────────────────────────────────────────────

class TestMarkToMarket:
    def test_yes_position_gains_when_price_rises(self, tmp_exec):
        asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="yes",
            size_usd=200, limit_price=0.62, book=_book(),
        ))
        # Entry 0.62, mark at 0.70 → profit
        tmp_exec.mark_to_market({"m1": 0.70})
        pos = tmp_exec.positions[0]
        assert pos.mark_price == pytest.approx(0.70)
        # (0.70 - 0.62) * contracts
        expected = (0.70 - 0.62) * pos.contracts
        assert pos.unrealized_pnl == pytest.approx(expected, abs=0.01)
        assert pos.unrealized_pnl > 0

    def test_yes_position_loses_when_price_falls(self, tmp_exec):
        asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="yes",
            size_usd=200, limit_price=0.62, book=_book(),
        ))
        tmp_exec.mark_to_market({"m1": 0.50})
        assert tmp_exec.positions[0].unrealized_pnl < 0

    def test_no_position_inverts_yes_price(self, tmp_exec):
        # Buy NO at limit 0.40; entry NO price = 0.40 (bid was 0.60)
        asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="no",
            size_usd=200, limit_price=0.40, book=_book(),
        ))
        # YES price falls to 0.50 → NO price rises to 0.50 → NO position gains
        tmp_exec.mark_to_market({"m1": 0.50})
        pos = tmp_exec.positions[0]
        assert pos.mark_price == pytest.approx(0.50)      # NO price
        assert pos.unrealized_pnl > 0

    def test_unknown_market_ignored(self, tmp_exec):
        asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="yes",
            size_usd=200, limit_price=0.62, book=_book(),
        ))
        tmp_exec.mark_to_market({"m99": 0.99})  # no position for m99
        assert tmp_exec.positions[0].unrealized_pnl == 0.0


# ── Close ─────────────────────────────────────────────────────────────────────

class TestClose:
    def test_close_removes_position_and_returns_pnl(self, tmp_exec):
        asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="yes",
            size_usd=200, limit_price=0.62, book=_book(),
        ))
        contracts = tmp_exec.positions[0].contracts
        pnl = tmp_exec.close_position("m1", yes_price=0.80)
        expected = (0.80 - 0.62) * contracts
        assert pnl == pytest.approx(expected, abs=0.01)
        assert len(tmp_exec.positions) == 0

    def test_close_unknown_returns_none(self, tmp_exec):
        assert tmp_exec.close_position("nope", yes_price=0.5) is None

    def test_close_no_side_inverts_price(self, tmp_exec):
        # Buy NO at 0.40, close when YES=0.50 (so NO=0.50) → profit
        asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="no",
            size_usd=200, limit_price=0.40, book=_book(),
        ))
        pnl = tmp_exec.close_position("m1", yes_price=0.50)
        assert pnl > 0

    def test_close_appends_to_closed_log(self, tmp_exec, tmp_path):
        asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="yes",
            size_usd=200, limit_price=0.62, book=_book(),
        ))
        tmp_exec.close_position("m1", yes_price=0.70)
        closed = (tmp_path / "closed_positions.jsonl").read_text().strip()
        rec = json.loads(closed)
        assert rec["event"] == "close"
        assert rec["market_id"] == "m1"
        assert "realized_pnl" in rec


# ── Summary / aggregates ──────────────────────────────────────────────────────

class TestSummary:
    def test_summary_empty(self, tmp_exec):
        s = tmp_exec.summary()
        assert s["open_positions"] == 0
        assert s["total_exposure_usd"] == 0.0
        assert s["total_unrealized_pnl"] == 0.0
        assert s["halted"] is False

    def test_summary_after_fills(self, tmp_exec):
        asyncio.run(tmp_exec.submit(
            market_id="m1", platform="poly", side="yes",
            size_usd=200, limit_price=0.62, book=_book(),
        ))
        asyncio.run(tmp_exec.submit(
            market_id="m2", platform="poly", side="yes",
            size_usd=150, limit_price=0.62, book=_book(),
        ))
        tmp_exec.mark_to_market({"m1": 0.70, "m2": 0.55})
        s = tmp_exec.summary()
        assert s["open_positions"] == 2
        assert s["total_exposure_usd"] == pytest.approx(350.0)
        # m1 profits, m2 loses -- net PnL is non-trivial
        assert s["total_unrealized_pnl"] != 0.0
