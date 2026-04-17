"""
Performance tracker: logs predictions and computes calibration metrics.

TODO: Persist to SQLite for easier querying.
TODO: Compute Brier score, log-loss, rolling accuracy.
TODO: Feed calibration errors back to predictor as bias offset.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.logging_setup import get_logger

logger = get_logger(__name__)
_LOG = Path("data/logs/predictions.jsonl")


@dataclass
class PredRecord:
    market_id: str
    p_model: float
    p_market: float
    edge: float
    side: str
    size_usd: float
    model_name: str
    resolved: bool = False
    outcome_correct: bool | None = None
    pnl: float | None = None
    predicted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: str | None = None


class PerformanceTracker:

    def __init__(self) -> None:
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        self._records: list[PredRecord] = []

    def record(self, rec: PredRecord) -> None:
        self._records.append(rec)
        with _LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec.__dict__) + "\n")

    def resolve(self, market_id: str, *, correct: bool, pnl: float) -> None:
        for rec in self._records:
            if rec.market_id == market_id and not rec.resolved:
                rec.resolved = True
                rec.outcome_correct = correct
                rec.pnl = pnl
                rec.resolved_at = datetime.now(timezone.utc).isoformat()
                logger.info("tracker.resolved", market_id=market_id, correct=correct, pnl=pnl)
                return

    def summary(self) -> dict:
        done = [r for r in self._records if r.resolved]
        if not done:
            return {"resolved": 0, "accuracy": None, "total_pnl": None}
        total_pnl = sum(r.pnl or 0 for r in done)
        return {
            "resolved": len(done),
            "accuracy": round(sum(1 for r in done if r.outcome_correct) / len(done), 4),
            "total_pnl": round(total_pnl, 2),
        }
