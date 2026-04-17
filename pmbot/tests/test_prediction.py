"""Tests for BaselinePredictor and PredictionEngine."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.config.rules import load_rules
from src.prediction.base import PredictionResult
from src.prediction.baseline import BaselinePredictor
from src.prediction.engine import PredictionEngine, Signal
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


# ── BaselinePredictor ────────────────────────────────────────────────────────

class TestBaselinePredictor:
    def setup_method(self):
        self.predictor = BaselinePredictor()

    def test_bullish_sentiment_raises_prob(self):
        market = _market()  # mid_price = 0.45
        research = _research(bullish=True)
        result = asyncio.run(self.predictor.predict(market, research))
        assert result.p_model > market.mid_price

    def test_bearish_sentiment_lowers_prob(self):
        market = _market(bid=0.54, ask=0.56)  # mid_price = 0.55
        research = _research(bearish=True)
        result = asyncio.run(self.predictor.predict(market, research))
        assert result.p_model < market.mid_price

    def test_neutral_sentiment_no_change(self):
        market = _market(bid=0.49, ask=0.51)  # mid_price = 0.50
        research = _research()
        result = asyncio.run(self.predictor.predict(market, research))
        assert result.p_model == pytest.approx(0.50, abs=0.01)

    def test_probability_clamped_to_valid_range(self):
        market = _market(bid=0.97, ask=0.99)  # mid_price = 0.98
        research = _research(bullish=True)
        result = asyncio.run(self.predictor.predict(market, research))
        assert 0.0 < result.p_model <= 0.98

    def test_edge_computed_correctly(self):
        market = _market()  # mid_price = 0.45
        research = _research()
        result = asyncio.run(self.predictor.predict(market, research))
        expected_edge = result.p_model - market.mid_price
        assert abs(result.edge - expected_edge) < 1e-6


# ── PredictionEngine ─────────────────────────────────────────────────────────

class TestPredictionEngine:
    def setup_method(self):
        self.rules = load_rules()
        self.engine = PredictionEngine(
            predictor=BaselinePredictor(),
            rules=self.rules,
        )

    def test_neutral_market_no_signal(self):
        """Neutral sentiment produces tiny edge -- should NOT pass the rules gate."""
        market = _market(bid=0.49, ask=0.51)
        research = _research()
        signal = asyncio.run(self.engine.run(market, research))
        assert isinstance(signal, Signal)
        # Baseline with no sentiment barely nudges off mid -- edge < min_edge
        assert signal.is_signal is False
        assert len(signal.failures) > 0

    def test_strong_sentiment_may_signal(self):
        """Strong bullish sentiment produces larger edge -- may pass if big enough."""
        market = _market(bid=0.30, ask=0.32)  # mid = 0.31
        research = _research(bullish=True)
        signal = asyncio.run(self.engine.run(market, research))
        # Bullish nudge is +0.10 max, so p_model ~0.41, edge ~0.10
        # min_edge default is 0.05 -> should pass edge check
        # But confidence is 0.40 and min_confidence default is 0.6 -> fails
        assert signal.is_signal is False
        assert any("confidence" in f for f in signal.failures)

    def test_signal_carries_prediction(self):
        """Signal always wraps the underlying PredictionResult."""
        market = _market()
        research = _research()
        signal = asyncio.run(self.engine.run(market, research))
        assert isinstance(signal.prediction, PredictionResult)
        assert signal.prediction.market_id == "m1"

    def test_prediction_fields(self):
        """PredictionResult has the expected fields."""
        market = _market()
        research = _research()
        signal = asyncio.run(self.engine.run(market, research))
        pred = signal.prediction
        assert hasattr(pred, "p_model")
        assert hasattr(pred, "p_market")
        assert hasattr(pred, "edge")
        assert hasattr(pred, "confidence")
        assert hasattr(pred, "recommended_side")
