"""
Baseline predictor.

Strategy: start from the market-implied probability and apply small
adjustments based on article sentiment and recency. This is intentionally
naive — it exists to give the pipeline something runnable before you wire
in a real model.

TODO: Replace with calibrated LLM-based forecaster.
TODO: Add ensemble: baseline + news sentiment + base-rate anchor.
"""
from __future__ import annotations

import re

from src.models import Market, Prediction
from src.research.researcher import ResearchResult
from src.utils import get_logger
from .base import BasePredictor

logger = get_logger(__name__)

# Very rough sentiment keywords
_BULLISH = {"will", "expects", "confirmed", "approved", "rising", "exceeds", "beats"}
_BEARISH = {"won't", "fails", "declined", "rejected", "falling", "below", "misses"}


def _sentiment_score(articles: list[dict]) -> float:
    """
    Returns a float in [-1, 1].
    Positive = bullish for YES outcome, negative = bearish.

    TODO: Replace keyword heuristic with a real sentiment model.
    """
    score = 0.0
    for art in articles:
        text = (art.get("title", "") + " " + art.get("description", "")).lower()
        tokens = set(re.findall(r"\w+", text))
        score += len(tokens & _BULLISH) - len(tokens & _BEARISH)
    # Normalize to [-0.1, 0.1] max nudge
    return max(-0.1, min(0.1, score * 0.01))


class BaselinePredictor(BasePredictor):
    model_name = "baseline_v1"

    async def predict(self, market: Market, research: ResearchResult) -> Prediction:
        market_prob = market.yes_probability or 0.5

        # Anchor to market, apply sentiment nudge
        sentiment = _sentiment_score(research.articles)
        raw_prob = market_prob + sentiment

        # Clip to valid range, avoid extreme values
        our_prob = max(0.02, min(0.98, raw_prob))

        logger.info(
            "prediction.baseline",
            market_id=market.id,
            market_prob=round(market_prob, 3),
            sentiment_nudge=round(sentiment, 4),
            our_prob=round(our_prob, 3),
        )

        return Prediction(
            market_id=market.id,
            our_probability=our_prob,
            market_probability=market_prob,
            confidence=0.4,   # low confidence until real model is wired
            model_name=self.model_name,
            rationale=f"Market anchor={market_prob:.2f}, sentiment nudge={sentiment:+.4f}",
        )
