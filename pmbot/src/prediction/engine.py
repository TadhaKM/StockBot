"""
PredictionEngine: wraps a predictor, applies rules gates, logs all predictions.

Every prediction is logged to JSONL regardless of whether it produces a signal.
Only predictions that pass edge + confidence thresholds become actionable signals.

Usage:
    engine = PredictionEngine(predictor=BaselinePredictor())
    signal = await engine.run(market, research)
    if signal.is_signal:
        # proceed to risk / execution
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.config.rules import TradingRules, load_rules, validate_edge
from src.logging_setup import get_logger
from src.research.researcher import ResearchResult
from src.scanner.base import Market
from .base import BasePredictor, PredictionResult

logger = get_logger(__name__)

_PRED_LOG = Path("data/logs/prediction_log.jsonl")


@dataclass
class Signal:
    """Wrapper around a PredictionResult that carries the rules verdict."""
    prediction: PredictionResult
    is_signal: bool
    failures: list[str]


class PredictionEngine:
    """Runs a predictor, applies edge/confidence rules, logs everything."""

    def __init__(
        self,
        predictor: BasePredictor,
        rules: TradingRules | None = None,
    ) -> None:
        self.predictor = predictor
        self.rules = rules or load_rules()
        _PRED_LOG.parent.mkdir(parents=True, exist_ok=True)

    async def run(self, market: Market, research: ResearchResult) -> Signal:
        pred = await self.predictor.predict(market, research)

        # Apply edge + confidence gate from trading_rules.yaml
        check = validate_edge(
            pred.p_model,
            pred.p_market,
            self.rules,
            confidence=pred.confidence,
        )

        signal = Signal(
            prediction=pred,
            is_signal=check.passed,
            failures=check.failures,
        )

        self._log(signal)

        if signal.is_signal:
            logger.info(
                "engine.signal",
                market_id=pred.market_id,
                edge=round(pred.edge, 4),
                confidence=pred.confidence,
                side=pred.recommended_side,
            )
        else:
            logger.info(
                "engine.no_signal",
                market_id=pred.market_id,
                edge=round(pred.edge, 4),
                confidence=pred.confidence,
                failures=signal.failures,
            )

        return signal

    def _log(self, signal: Signal) -> None:
        pred = signal.prediction
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "market_id": pred.market_id,
            "model": pred.model_name,
            "p_model": round(pred.p_model, 6),
            "p_market": round(pred.p_market, 6),
            "edge": round(pred.edge, 6),
            "confidence": pred.confidence,
            "side": pred.recommended_side,
            "is_signal": signal.is_signal,
            "failures": signal.failures,
            "rationale": pred.rationale,
        }
        with _PRED_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
