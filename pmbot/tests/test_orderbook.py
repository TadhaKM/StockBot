"""Tests for the order book evaluation module."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.config.rules import load_rules, TradingRules
from src.execution.orderbook import FillEstimate, OrderBook
from src.scanner.base import Market


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _book() -> OrderBook:
    """Standard 3-level book."""
    return OrderBook(
        bids=[(0.60, 500), (0.59, 300), (0.58, 200)],
        asks=[(0.62, 400), (0.63, 350), (0.64, 100)],
    )


def _thin_book() -> OrderBook:
    """Book with almost no liquidity."""
    return OrderBook(
        bids=[(0.50, 10)],
        asks=[(0.55, 10)],
    )


def _rules() -> TradingRules:
    return load_rules()


# ── Properties ────────────────────────────────────────────────────────────────

class TestOrderBookProperties:
    def test_best_bid(self):
        assert _book().best_bid == 0.60

    def test_best_ask(self):
        assert _book().best_ask == 0.62

    def test_spread(self):
        assert _book().spread == pytest.approx(0.02)

    def test_mid_price(self):
        assert _book().mid_price == pytest.approx(0.61)

    def test_total_bid_depth(self):
        assert _book().total_bid_depth == 1000  # 500 + 300 + 200

    def test_total_ask_depth(self):
        assert _book().total_ask_depth == 850   # 400 + 350 + 100

    def test_empty_book_defaults(self):
        empty = OrderBook()
        assert empty.best_bid == 0.0
        assert empty.best_ask == 1.0
        assert empty.spread == 1.0


# ── Depth ─────────────────────────────────────────────────────────────────────

class TestDepthWithin:
    def test_depth_within_default_band(self):
        book = _book()
        # mid = 0.61, band = 0.02 → [0.59, 0.63]
        # bids in range: 0.60 (500) + 0.59 (300) = 800
        # asks in range: 0.62 (400) + 0.63 (350) = 750
        depth = book.depth_within(0.02)
        assert depth == 1550

    def test_narrow_band(self):
        book = _book()
        # mid = 0.61, band = 0.01 → [0.60, 0.62]
        # bids: 0.60 (500)
        # asks: 0.62 (400)
        depth = book.depth_within(0.01)
        assert depth == 900

    def test_zero_band(self):
        book = _book()
        # Nothing exactly at mid
        depth = book.depth_within(0.0)
        assert depth == 0.0


# ── Fill estimation ───────────────────────────────────────────────────────────

class TestEstimateFillPrice:
    def test_buy_within_top_level(self):
        book = _book()
        fill = book.estimate_fill_price("yes", 200)
        # Entirely filled at best ask 0.62
        assert fill.fill_price == pytest.approx(0.62)
        assert fill.slippage == pytest.approx(0.0)
        assert fill.levels_consumed == 1
        assert fill.fully_filled is True

    def test_buy_walks_two_levels(self):
        book = _book()
        # Need 600 USD: 400 at 0.62 + 200 at 0.63
        fill = book.estimate_fill_price("yes", 600)
        expected_vwap = (400 * 0.62 + 200 * 0.63) / 600
        assert fill.fill_price == pytest.approx(expected_vwap, abs=1e-4)
        assert fill.slippage == pytest.approx(expected_vwap - 0.62, abs=1e-4)
        assert fill.levels_consumed == 2
        assert fill.fully_filled is True

    def test_buy_walks_all_levels(self):
        book = _book()
        fill = book.estimate_fill_price("yes", 850)
        # 400 at 0.62 + 350 at 0.63 + 100 at 0.64 = 850
        assert fill.levels_consumed == 3
        assert fill.fully_filled is True

    def test_buy_exceeds_book(self):
        book = _book()
        fill = book.estimate_fill_price("yes", 1000)
        # Total ask depth = 850
        assert fill.fully_filled is False
        assert fill.filled_usd == 850

    def test_sell_within_top_level(self):
        book = _book()
        fill = book.estimate_fill_price("no", 300)
        assert fill.fill_price == pytest.approx(0.60)
        assert fill.slippage == pytest.approx(0.0)
        assert fill.levels_consumed == 1

    def test_sell_walks_book(self):
        book = _book()
        # 500 at 0.60 + 200 at 0.59 = 700
        fill = book.estimate_fill_price("no", 700)
        expected_vwap = (500 * 0.60 + 200 * 0.59) / 700
        assert fill.fill_price == pytest.approx(expected_vwap, abs=1e-4)
        assert fill.slippage == pytest.approx(0.60 - expected_vwap, abs=1e-4)
        assert fill.levels_consumed == 2

    def test_empty_book_not_filled(self):
        book = OrderBook()
        fill = book.estimate_fill_price("yes", 100)
        assert fill.fully_filled is False
        assert fill.filled_usd == 0.0


# ── Trade safety ──────────────────────────────────────────────────────────────

class TestIsTradeSafe:
    def test_safe_small_order(self):
        book = _book()
        result = book.is_trade_safe("yes", 200, _rules())
        assert result.passed is True

    def test_rejects_thin_book(self):
        book = _thin_book()
        result = book.is_trade_safe("yes", 5, _rules())
        assert result.passed is False
        assert any("depth" in f for f in result.failures)

    def test_rejects_unfillable_order(self):
        book = _book()
        result = book.is_trade_safe("yes", 5000, _rules())
        assert result.passed is False
        assert any("thin" in f for f in result.failures)

    def test_rejects_high_slippage(self):
        # Book where all liquidity is at one tight level, then a huge gap
        book = OrderBook(
            bids=[(0.50, 1000)],
            asks=[(0.52, 10), (0.70, 1000)],  # 10 USD at 0.52, rest at 0.70
        )
        # Buying 500 USD: 10 at 0.52 + 490 at 0.70 → vwap ≈ 0.6964 → slippage ≈ 0.18
        result = book.is_trade_safe("yes", 500, _rules())
        assert result.passed is False
        assert any("slippage" in f for f in result.failures)


# ── Synthetic book from Market ────────────────────────────────────────────────

class TestFromMarket:
    def test_creates_correct_levels(self):
        market = Market(
            id="test",
            title="Test",
            platform="test",
            bid=0.50,
            ask=0.52,
            volume_usd=100_000,
            orderbook_depth=5_000,
            close_time=datetime.now(timezone.utc) + timedelta(days=10),
        )
        book = OrderBook.from_market(market, levels=5)
        assert len(book.bids) == 5
        assert len(book.asks) == 5
        assert book.best_bid == 0.50
        assert book.best_ask == 0.52

    def test_depth_is_distributed(self):
        market = Market(
            id="test",
            title="Test",
            platform="test",
            bid=0.50,
            ask=0.52,
            volume_usd=100_000,
            orderbook_depth=5_000,
            close_time=datetime.now(timezone.utc) + timedelta(days=10),
        )
        book = OrderBook.from_market(market, levels=5)
        # Total depth across all levels = 5000 (split bid + ask)
        # Each side gets 5 levels × 1000 = 5000, total = 10000?
        # No — each level gets orderbook_depth / levels = 1000
        # bid depth = 5 × 1000 = 5000, ask depth = 5 × 1000 = 5000
        assert book.total_bid_depth == pytest.approx(5000, abs=1)
        assert book.total_ask_depth == pytest.approx(5000, abs=1)
