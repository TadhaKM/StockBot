"""Tests for BaselinePredictor."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.prediction.base import PredictionResult
from src.prediction.baseline import BaselinePredictor
from src.research.researcher import ResearchResult
from src.scanner.base import Market


def _market(bid: float = 0.44, ask: float = 0.46) -> Market:
    return Market(
        id="m1",
        title="Will X happen?",
        platform="polymarket",
        bid=bid,
        ask=ask,
        volume_usd=100_000.0,
        orderbook_depth=5_000.0,
        close_time=datetime.now(timezone.utc) + timedelta(days=7),
        category="politics",
    )


def _research(*, bullish: bool = False, bearish: bool = False) -> ResearchResult:
    articles: list[dict] = []
    if bullish:
        articles = [{"title": "rising beats confirmed approved", "description": "rising"}] * 10
    elif bearish:
        articles = [{"title": "fails declined rejected falling", "description": "falling"}] * 10
    return ResearchResult(market_id="m1", articles=articles)


class TestBaselinePredictor:
    def setup_method(self):
        self.predictor = BaselinePredictor()

    def test_bullish_sentiment_raises_prob(self):
        market = _market()  # mid_price = 0.45
        research = _research(bullish=True)
        result = asyncio.run(self.predictor.predict(market, research))
        assert result.our_probability > market.mid_price

    def test_bearish_sentiment_lowers_prob(self):
        market = _market(bid=0.54, ask=0.56)  # mid_price = 0.55
        research = _research(bearish=True)
        result = asyncio.run(self.predictor.predict(market, research))
        assert result.our_probability < market.mid_price

    def test_neutral_sentiment_no_change(self):
        market = _market(bid=0.49, ask=0.51)  # mid_price = 0.50
        research = _research()
        result = asyncio.run(self.predictor.predict(market, research))
        assert result.our_probability == pytest.approx(0.50, abs=0.01)

    def test_probability_clamped_to_valid_range(self):
        market = _market(bid=0.97, ask=0.99)  # mid_price = 0.98
        research = _research(bullish=True)
        result = asyncio.run(self.predictor.predict(market, research))
        assert 0.0 < result.our_probability <= 0.98

    def test_edge_computed_correctly(self):
        market = _market()  # mid_price = 0.45
        research = _research()
        result = asyncio.run(self.predictor.predict(market, research))
        expected_edge = result.our_probability - market.mid_price
        assert abs(result.edge - expected_edge) < 1e-6
