"""Tests for MarketFilter and ranking."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.filter.market_filter import MarketFilter, ranking_score
from src.config.rules import load_rules
from src.scanner.base import Market


def _market(
    *,
    market_id: str = "m1",
    bid: float = 0.48,
    ask: float = 0.50,
    category: str = "politics",
    close_time: datetime | None = None,
    volume_usd: float = 50_000.0,
    orderbook_depth: float = 5_000.0,
    platform: str = "polymarket",
) -> Market:
    if close_time is None:
        close_time = datetime.now(timezone.utc) + timedelta(days=10)
    return Market(
        id=market_id,
        title="Test market",
        platform=platform,
        bid=bid,
        ask=ask,
        close_time=close_time,
        volume_usd=volume_usd,
        orderbook_depth=orderbook_depth,
        category=category,
    )


class TestMarketFilter:
    def setup_method(self):
        self.f = MarketFilter()

    def test_passes_valid_market(self):
        result = self.f.run([_market()])
        assert len(result) == 1

    def test_blocks_low_volume(self):
        result = self.f.run([_market(volume_usd=10)])
        assert len(result) == 0

    def test_blocks_wide_spread(self):
        # spread = 0.50 - 0.10 = 0.40, far above max_spread=0.03
        result = self.f.run([_market(bid=0.10, ask=0.50)])
        assert len(result) == 0

    def test_blocks_shallow_orderbook(self):
        result = self.f.run([_market(orderbook_depth=10)])
        assert len(result) == 0

    def test_blocks_far_expiry(self):
        far_out = datetime.now(timezone.utc) + timedelta(days=365)
        result = self.f.run([_market(close_time=far_out)])
        assert len(result) == 0

    def test_multiple_markets_partial_pass(self):
        markets = [
            _market(market_id="good"),
            _market(market_id="bad_vol", volume_usd=10),
        ]
        result = self.f.run(markets)
        assert len(result) == 1
        assert result[0].market.id == "good"

    def test_results_sorted_by_score_descending(self):
        markets = [
            _market(market_id="low_vol", volume_usd=1_000),
            _market(market_id="high_vol", volume_usd=500_000),
        ]
        result = self.f.run(markets)
        assert len(result) == 2
        assert result[0].market.id == "high_vol"
        assert result[0].score >= result[1].score


class TestRankingScore:
    def setup_method(self):
        self.rules = load_rules()

    def test_score_is_between_0_and_100(self):
        m = _market()
        s = ranking_score(m, self.rules)
        assert 0 <= s <= 100

    def test_higher_volume_gives_higher_score(self):
        low = _market(volume_usd=1_000)
        high = _market(volume_usd=500_000)
        assert ranking_score(high, self.rules) > ranking_score(low, self.rules)

    def test_tighter_spread_gives_higher_score(self):
        wide = _market(bid=0.45, ask=0.48)   # spread=0.03
        tight = _market(bid=0.49, ask=0.50)  # spread=0.01
        assert ranking_score(tight, self.rules) > ranking_score(wide, self.rules)
