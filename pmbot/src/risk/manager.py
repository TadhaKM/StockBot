"""Risk manager: gates a prediction through all checks and returns a sized decision."""
from __future__ import annotations

from dataclasses import dataclass

from src.config import cfg
from src.logging_setup import get_logger
from src.prediction.base import PredictionResult
from .kelly import kelly_size

logger = get_logger(__name__)


@dataclass
class SizingDecision:
    approved: bool
    size_usd: float
    reason: str


class RiskManager:

    def __init__(self, open_market_ids: set[str] | None = None) -> None:
        self.open_market_ids = open_market_ids or set()

    def evaluate(self, pred: PredictionResult) -> SizingDecision:
        rc = cfg.risk

        if abs(pred.edge) < rc.min_edge_threshold:
            return SizingDecision(False, 0.0, f"edge {pred.edge:.4f} below threshold {rc.min_edge_threshold}")

        if len(self.open_market_ids) >= rc.max_open_positions:
            return SizingDecision(False, 0.0, "max open positions reached")

        if pred.market_id in self.open_market_ids:
            return SizingDecision(False, 0.0, "already holding this market")

        if pred.confidence < cfg.prediction.min_confidence:
            return SizingDecision(False, 0.0, f"confidence {pred.confidence} below minimum")

        price = pred.market_probability if pred.edge > 0 else 1 - pred.market_probability
        prob = pred.our_probability if pred.edge > 0 else 1 - pred.our_probability

        size = kelly_size(
            rc.bankroll_usd,
            prob,
            price,
            fractional=rc.kelly_fraction,
            max_fraction=rc.max_bankroll_fraction,
        )
        if size <= 0:
            return SizingDecision(False, 0.0, "Kelly sizing returned 0")

        logger.info("risk.approved", market_id=pred.market_id, edge=round(pred.edge, 4), size_usd=size)
        return SizingDecision(True, size, "all checks passed")
