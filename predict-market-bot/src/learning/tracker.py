"""
Performance tracker — records predictions vs outcomes and computes calibration.

Calibration score: how well our stated probabilities match actual frequencies.
A perfectly calibrated forecaster predicts 70% → outcome happens 70% of the time.

TODO: Persist to SQLite instead of JSONL for easier querying.
TODO: Add Brier score, log loss, and rolling metrics.
TODO: Feed calibration errors back to predictor as bias correction.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.utils import get_logger

logger = get_logger(__name__)

_LOG_PATH = Path("data/logs/predictions.jsonl")


@dataclass
class PredictionRecord:
    market_id: str
    our_probability: float
    market_probability: float
    edge: float
    side: str
    size_usd: float
    resolved: bool = False
    outcome_correct: bool | None = None
    pnl: float | None = None
    predicted_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    resolved_at: str | None = None


class PerformanceTracker:

    def __init__(self) -> None:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._records: list[PredictionRecord] = []

    def record(self, rec: PredictionRecord) -> None:
        self._records.append(rec)
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec.__dict__) + "\n")
        logger.info("tracker.recorded", market_id=rec.market_id, edge=round(rec.edge, 4))

    def resolve(self, market_id: str, *, outcome_correct: bool, pnl: float) -> None:
        for rec in self._records:
            if rec.market_id == market_id and not rec.resolved:
                rec.resolved = True
                rec.outcome_correct = outcome_correct
                rec.pnl = pnl
                rec.resolved_at = datetime.utcnow().isoformat()
                logger.info(
                    "tracker.resolved",
                    market_id=market_id,
                    correct=outcome_correct,
                    pnl=pnl,
                )
                return

    def summary(self) -> dict:
        resolved = [r for r in self._records if r.resolved]
        if not resolved:
            return {"resolved": 0}

        correct = sum(1 for r in resolved if r.outcome_correct)
        total_pnl = sum(r.pnl or 0 for r in resolved)
        accuracy = correct / len(resolved)

        # TODO: Compute Brier score and log-loss here
        return {
            "resolved": len(resolved),
            "accuracy": round(accuracy, 4),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(total_pnl / len(resolved), 2),
        }
