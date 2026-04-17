"""Tests for BaselinePredictor."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.prediction.base import PredictionResult
from src.prediction.baseline import BaselinePredictor
from src.research.researcher import ResearchResult
from src.scanner.base import Market


def _market(yes_probability: float = 0.45) -> Market:
    return Market(
        id="m1",
        question="Will X happen?",
        platform="polymarket",
        yes_probability=yes_probability,
        close_time=datetime.now(timezone.utc) + timedelta(days=7),
        volume_usd=100_000.0,
        category="politics",
    )


def _research(*, bullish: bool = False, bearish: bool = False) -> ResearchResult:
    """Build a ResearchResult with articles containing bullish or bearish keywords."""
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
        market = _market(yes_probability=0.45)
        research = _research(bullish=True)
        result = asyncio.run(self.predictor.predict(market, research))
        assert result.our_probability > market.yes_probability

    def test_bearish_sentiment_lowers_prob(self):
        market = _market(yes_probability=0.55)
        research = _research(bearish=True)
        result = asyncio.run(self.predictor.predict(market, research))
        assert result.our_probability < market.yes_probability

    def test_neutral_sentiment_no_change(self):
        market = _market(yes_probability=0.50)
        research = _research()
        result = asyncio.run(self.predictor.predict(market, research))
        assert result.our_probability == pytest.approx(0.50, abs=0.01)

    def test_probability_clamped_to_valid_range(self):
        market = _market(yes_probability=0.98)
        research = _research(bullish=True)
        result = asyncio.run(self.predictor.predict(market, research))
        assert 0.0 < result.our_probability <= 0.98

    def test_edge_computed_correctly(self):
        market = _market(yes_probability=0.45)
        research = _research()
        result = asyncio.run(self.predictor.predict(market, research))
        expected_edge = result.our_probability - market.yes_probability
        assert abs(result.edge - expected_edge) < 1e-6
