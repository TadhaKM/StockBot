"""Tests for BaselinePredictor."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.prediction.base import PredictionResult
from src.prediction.baseline import BaselinePredictor
from src.research.researcher import ResearchResult
from src.scanner.base import Market


def _market(yes_price: float = 0.45) -> Market:
    return Market(
        id="m1",
        title="Will X happen?",
        platform="polymarket",
        yes_price=yes_price,
        close_time=datetime.now(timezone.utc) + timedelta(days=7),
        volume_usd=100_000.0,
        category="politics",
    )


def _research(sentiment: float = 0.0) -> ResearchResult:
    return ResearchResult(
        market_id="m1",
        headlines=[],
        sentiment_score=sentiment,
        summary="No data.",
    )


class TestBaselinePredictor:
    def setup_method(self):
        self.predictor = BaselinePredictor()

    def test_bullish_sentiment_raises_prob(self):
        market = _market(yes_price=0.45)
        research = _research(sentiment=0.8)
        result = asyncio.run(self.predictor.predict(market, research))
        assert result.our_probability > market.yes_price

    def test_bearish_sentiment_lowers_prob(self):
        market = _market(yes_price=0.55)
        research = _research(sentiment=-0.8)
        result = asyncio.run(self.predictor.predict(market, research))
        assert result.our_probability < market.yes_price

    def test_neutral_sentiment_no_change(self):
        market = _market(yes_price=0.50)
        research = _research(sentiment=0.0)
        result = asyncio.run(self.predictor.predict(market, research))
        assert abs(result.our_probability - 0.50) < 0.01

    def test_probability_clamped_to_valid_range(self):
        market = _market(yes_price=0.95)
        research = _research(sentiment=1.0)
        result = asyncio.run(self.predictor.predict(market, research))
        assert 0.0 < result.our_probability < 1.0

    def test_edge_computed_correctly(self):
        market = _market(yes_price=0.45)
        research = _research(sentiment=0.5)
        result = asyncio.run(self.predictor.predict(market, research))
        expected_edge = result.our_probability - market.yes_price
        assert abs(result.edge - expected_edge) < 1e-6
