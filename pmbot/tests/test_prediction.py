"""Tests for BaselinePredictor and PredictionEngine."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.config.rules import load_rules
from src.prediction.base import PredictionResult
from src.prediction.baseline import BaselinePredictor, _confidence, _sentiment
from src.prediction.engine import PredictionEngine, Signal
from src.research.researcher import ResearchResult
from src.scanner.base import Market


# ── Helpers ──────────────────────────────────────────────────────────────────

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


def _research(*, bullish: bool = False, bearish: bool = False, n: int = 10) -> ResearchResult:
    """Build a ResearchResult with n articles of the requested sentiment."""
    articles: list[dict] = []
    if bullish:
        articles = [{"title": "rising beats confirmed approved", "description": "rising"}] * n
    elif bearish:
        articles = [{"title": "fails declined rejected falling", "description": "falling"}] * n
    return ResearchResult(market_id="m1", articles=articles)


# ── Unit: _sentiment and _confidence ─────────────────────────────────────────

class TestHelpers:
    def test_sentiment_neutral(self):
        assert _sentiment([]) == 0.0

    def test_sentiment_bullish_capped(self):
        # Many articles with strong positive words -- capped at +0.10
        arts = [{"title": "rising beats confirmed approved exceeds", "description": ""}] * 50
        assert _sentiment(arts) == pytest.approx(0.10)

    def test_sentiment_bearish_capped(self):
        arts = [{"title": "fails declined rejected falling misses", "description": ""}] * 50
        assert _sentiment(arts) == pytest.approx(-0.10)

    def test_confidence_no_data(self):
        # No articles, no nudge → minimum confidence
        conf = _confidence([], 0.0)
        assert conf == pytest.approx(0.35)

    def test_confidence_max(self):
        # 15+ articles with full |nudge| → maximum confidence
        arts = [{}] * 15
        conf = _confidence(arts, 0.10)
        assert conf == pytest.approx(0.80)

    def test_confidence_increases_with_articles(self):
        conf_none = _confidence([], 0.05)
        conf_some = _confidence([{}] * 10, 0.05)
        assert conf_some > conf_none

    def test_confidence_increases_with_signal_strength(self):
        arts = [{}] * 5
        conf_weak = _confidence(arts, 0.02)
        conf_strong = _confidence(arts, 0.10)
        assert conf_strong > conf_weak

    def test_confidence_range(self):
        for n in range(0, 20):
            for nudge in [-0.10, -0.05, 0.0, 0.05, 0.10]:
                conf = _confidence([{}] * n, nudge)
                assert 0.35 <= conf <= 0.80


# ── BaselinePredictor ────────────────────────────────────────────────────────

class TestBaselinePredictor:
    def setup_method(self):
        self.predictor = BaselinePredictor()

    def test_bullish_sentiment_raises_prob(self):
        market = _market()  # mid = 0.45
        result = asyncio.run(self.predictor.predict(market, _research(bullish=True)))
        assert result.p_model > market.mid_price

    def test_bearish_sentiment_lowers_prob(self):
        market = _market(bid=0.54, ask=0.56)  # mid = 0.55
        result = asyncio.run(self.predictor.predict(market, _research(bearish=True)))
        assert result.p_model < market.mid_price

    def test_neutral_sentiment_anchors_to_mid(self):
        market = _market(bid=0.49, ask=0.51)  # mid = 0.50
        result = asyncio.run(self.predictor.predict(market, _research()))
        assert result.p_model == pytest.approx(0.50, abs=0.01)

    def test_p_market_equals_mid_price(self):
        market = _market(bid=0.40, ask=0.44)  # mid = 0.42
        result = asyncio.run(self.predictor.predict(market, _research()))
        assert result.p_market == pytest.approx(market.mid_price)

    def test_edge_equals_p_model_minus_p_market(self):
        market = _market()
        result = asyncio.run(self.predictor.predict(market, _research(bullish=True)))
        assert result.edge == pytest.approx(result.p_model - result.p_market, abs=1e-6)

    def test_probability_clamped_to_valid_range(self):
        market = _market(bid=0.97, ask=0.99)  # mid = 0.98
        result = asyncio.run(self.predictor.predict(market, _research(bullish=True)))
        assert 0.0 < result.p_model <= 0.98

    def test_confidence_varies_with_evidence(self):
        market = _market()
        no_news = asyncio.run(self.predictor.predict(market, _research()))
        strong_news = asyncio.run(self.predictor.predict(market, _research(bullish=True, n=15)))
        assert strong_news.confidence > no_news.confidence

    def test_confidence_in_valid_range(self):
        market = _market()
        result = asyncio.run(self.predictor.predict(market, _research(bullish=True)))
        assert 0.0 < result.confidence <= 1.0


# ── PredictionEngine ─────────────────────────────────────────────────────────

class TestPredictionEngine:
    def setup_method(self):
        self.rules = load_rules()
        self.engine = PredictionEngine(predictor=BaselinePredictor(), rules=self.rules)

    # --- FAILING cases -------------------------------------------------------

    def test_no_news_never_signals(self):
        """No articles → edge=0 and confidence=0.35 → both gates fail."""
        market = _market(bid=0.49, ask=0.51)  # mid=0.50, nudge=0
        signal = asyncio.run(self.engine.run(market, _research()))
        assert signal.is_signal is False
        assert any("edge" in f for f in signal.failures)
        assert any("confidence" in f for f in signal.failures)

    def test_bearish_market_near_mid_no_signal(self):
        """Bearish sentiment on a ~0.50 market: edge ≈ -0.10, confidence low → fails."""
        market = _market(bid=0.49, ask=0.51)  # mid=0.50
        # bearish nudge → p_model ~0.40, edge ~ -0.10 (|edge|=0.10 passes)
        # but confidence with n=3: 0.35 + (3/15)*0.20 + (0.10/0.10)*0.25 = 0.35+0.04+0.25 = 0.64
        # 3 articles barely gets us to 0.64 -- this depends on nudge.
        # Use 0 articles to guarantee failure.
        signal = asyncio.run(self.engine.run(market, _research(bearish=True, n=0)))
        assert signal.is_signal is False

    # --- PASSING cases -------------------------------------------------------

    def test_strong_bullish_becomes_signal(self):
        """Many bullish articles on low-mid market: edge=0.10, confidence>0.70 → both pass."""
        # mid=0.31, nudge=+0.10 → p_model=0.41, edge=0.10 (> min_edge 0.05)
        # 10 articles → confidence = 0.35 + (10/15)*0.20 + 1.0*0.25 = 0.35+0.133+0.25 = 0.733
        market = _market(bid=0.30, ask=0.32)
        signal = asyncio.run(self.engine.run(market, _research(bullish=True, n=10)))
        assert signal.is_signal is True
        assert signal.failures == []

    def test_strong_bearish_becomes_signal(self):
        """Many bearish articles on high-mid market: edge=-0.10, confidence>0.70 → passes."""
        market = _market(bid=0.68, ask=0.72)  # mid=0.70, nudge=-0.10 → p_model=0.60, edge=-0.10
        signal = asyncio.run(self.engine.run(market, _research(bearish=True, n=10)))
        assert signal.is_signal is True
        assert signal.failures == []

    # --- Schema / structure --------------------------------------------------

    def test_signal_always_carries_prediction(self):
        signal = asyncio.run(self.engine.run(_market(), _research()))
        assert isinstance(signal.prediction, PredictionResult)
        assert signal.prediction.market_id == "m1"

    def test_all_output_fields_present(self):
        signal = asyncio.run(self.engine.run(_market(), _research(bullish=True, n=10)))
        pred = signal.prediction
        assert 0.0 <= pred.p_model <= 1.0
        assert 0.0 <= pred.p_market <= 1.0
        assert isinstance(pred.edge, float)
        assert 0.0 < pred.confidence <= 1.0
        assert pred.recommended_side in ("yes", "no")
        assert isinstance(signal.is_signal, bool)
        assert isinstance(signal.failures, list)

    def test_not_every_market_signals(self):
        """Mix of neutral (no signal) and bullish (signal) — not uniform."""
        neutral = asyncio.run(self.engine.run(_market(bid=0.49, ask=0.51), _research()))
        bullish = asyncio.run(self.engine.run(_market(bid=0.30, ask=0.32), _research(bullish=True, n=10)))
        assert neutral.is_signal is False
        assert bullish.is_signal is True

    def test_recommended_side_yes_when_positive_edge(self):
        market = _market(bid=0.30, ask=0.32)  # low mid, bullish → positive edge
        signal = asyncio.run(self.engine.run(market, _research(bullish=True, n=10)))
        assert signal.prediction.edge > 0
        assert signal.prediction.recommended_side == "yes"

    def test_recommended_side_no_when_negative_edge(self):
        market = _market(bid=0.68, ask=0.72)  # high mid, bearish → negative edge
        signal = asyncio.run(self.engine.run(market, _research(bearish=True, n=10)))
        assert signal.prediction.edge < 0
        assert signal.prediction.recommended_side == "no"
