"""Tests for MarketFilter."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.filter.market_filter import MarketFilter
from src.scanner.base import Market


def _market(
    *,
    market_id: str = "m1",
    yes_probability: float = 0.5,
    category: str = "politics",
    close_time: datetime | None = None,
    volume_usd: float = 50_000.0,
    platform: str = "polymarket",
) -> Market:
    if close_time is None:
        close_time = datetime.now(timezone.utc) + timedelta(days=10)
    return Market(
        id=market_id,
        question="Will X happen?",
        platform=platform,
        yes_probability=yes_probability,
        close_time=close_time,
        volume_usd=volume_usd,
        category=category,
    )


class TestMarketFilter:
    def setup_method(self):
        self.f = MarketFilter()

    def test_passes_valid_market(self):
        result = self.f.run([_market()])
        assert len(result) == 1

    def test_blocks_extreme_probability_high(self):
        result = self.f.run([_market(yes_probability=0.98)])
        assert len(result) == 0

    def test_blocks_extreme_probability_low(self):
        result = self.f.run([_market(yes_probability=0.02)])
        assert len(result) == 0

    def test_blocks_excluded_category(self):
        # "test" is in blocked_categories in default.yaml
        result = self.f.run([_market(category="test")])
        assert len(result) == 0

    def test_allows_boundary_probability(self):
        # 0.05 is the min; should pass
        result = self.f.run([_market(yes_probability=0.05)])
        assert len(result) == 1

    def test_multiple_markets_partial_pass(self):
        markets = [
            _market(market_id="good"),
            _market(market_id="bad", yes_probability=0.99),
        ]
        result = self.f.run(markets)
        assert len(result) == 1
        assert result[0].id == "good"
