"""
Baseline predictor: anchors to market mid-price, adds a tiny sentiment nudge.
Intentionally naive — gives the pipeline something to run before a real model is wired in.

TODO: Replace with calibrated LLM-based forecaster.
TODO: Add ensemble weighting (baseline + base-rate + news model).
"""
from __future__ import annotations

import re

from src.logging_setup import get_logger
from src.research.researcher import ResearchResult
from src.scanner.base import Market
from .base import BasePredictor, PredictionResult

logger = get_logger(__name__)

_POSITIVE = {"will", "expects", "confirmed", "approved", "rising", "beats", "exceeds"}
_NEGATIVE = {"won't", "fails", "declined", "rejected", "falling", "misses", "below"}


def _sentiment(articles: list[dict]) -> float:
    """Returns [-0.10, +0.10] nudge. TODO: replace with real model."""
    score = 0.0
    for a in articles:
        text = (a.get("title", "") + " " + a.get("description", "")).lower()
        tokens = set(re.findall(r"\w+", text))
        score += len(tokens & _POSITIVE) - len(tokens & _NEGATIVE)
    return max(-0.10, min(0.10, score * 0.01))


def _confidence(articles: list[dict], nudge: float) -> float:
    """
    Confidence score based on quantity of evidence and strength of signal.

    Components (all additive on top of a 0.35 base):
      data_score   : up to +0.20  (saturates at 15 articles)
      signal_score : up to +0.25  (proportional to |nudge|, max at 0.10)

    Range: [0.35, 0.80]

    Intuition:
      - No news, no sentiment       → 0.35  (almost no basis for prediction)
      - Many articles, weak signal  → ~0.50 (data present but directionless)
      - Few articles, strong signal → ~0.60 (clear direction, thin evidence)
      - Many articles, strong signal→ ~0.80 (high conviction)
    """
    data_score = min(len(articles), 15) / 15 * 0.20
    signal_score = (abs(nudge) / 0.10) * 0.25
    return round(max(0.35, min(0.80, 0.35 + data_score + signal_score)), 4)


class BaselinePredictor(BasePredictor):
    name = "baseline_v1"

    async def predict(self, market: Market, research: ResearchResult) -> PredictionResult:
        nudge = _sentiment(research.articles)
        p_model = max(0.02, min(0.98, market.mid_price + nudge))
        confidence = _confidence(research.articles, nudge)

        logger.info(
            "prediction.baseline",
            market_id=market.id,
            mid_price=round(market.mid_price, 3),
            nudge=round(nudge, 4),
            p_model=round(p_model, 3),
            confidence=confidence,
        )
        return PredictionResult(
            market_id=market.id,
            p_model=p_model,
            p_market=market.mid_price,
            confidence=confidence,
            model_name=self.name,
            rationale=f"mid={market.mid_price:.2f} nudge={nudge:+.4f} conf={confidence:.2f}",
        )
