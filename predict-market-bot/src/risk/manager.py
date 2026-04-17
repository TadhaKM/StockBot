"""Risk manager — decides whether a trade passes all gates before execution."""
from __future__ import annotations

from dataclasses import dataclass

from src.config import settings
from src.models import Position, Prediction
from src.utils import get_logger
from .kelly import kelly_size

logger = get_logger(__name__)


@dataclass
class SizingDecision:
    approved: bool
    size_usd: float
    reason: str


class RiskManager:
    """
    Gates a trade through several risk checks and returns a sized decision.

    Checks (in order):
      1. Edge meets minimum threshold
      2. Open position count below max
      3. Duplicate position (already holding this market)
      4. Kelly sizing
      5. Hard cap per trade
    """

    def __init__(
        self,
        bankroll: float,
        open_positions: list[Position] | None = None,
    ) -> None:
        self.bankroll = bankroll
        self.open_positions = open_positions or []

    def evaluate(self, prediction: Prediction) -> SizingDecision:
        # 1. Edge check
        if abs(prediction.edge) < settings.min_edge_threshold:
            return SizingDecision(
                approved=False,
                size_usd=0.0,
                reason=f"Edge {prediction.edge:.4f} below threshold {settings.min_edge_threshold}",
            )

        # 2. Position count
        if len(self.open_positions) >= settings.max_open_positions:
            return SizingDecision(
                approved=False,
                size_usd=0.0,
                reason=f"Max open positions ({settings.max_open_positions}) reached",
            )

        # 3. Duplicate check
        held_ids = {p.market_id for p in self.open_positions}
        if prediction.market_id in held_ids:
            return SizingDecision(
                approved=False,
                size_usd=0.0,
                reason="Already holding a position in this market",
            )

        # 4 & 5. Kelly sizing with hard cap
        market_price = prediction.market_probability
        if prediction.edge < 0:
            # Edge is on the NO side — adjust price
            market_price = 1 - prediction.market_probability
            our_prob = 1 - prediction.our_probability
        else:
            our_prob = prediction.our_probability

        size = kelly_size(
            bankroll=self.bankroll,
            our_prob=our_prob,
            market_price=market_price,
            fractional=settings.kelly_fraction,
            max_fraction=settings.max_bankroll_fraction,
        )

        if size <= 0:
            return SizingDecision(approved=False, size_usd=0.0, reason="Kelly sizing returned 0")

        logger.info(
            "risk.approved",
            market_id=prediction.market_id,
            edge=round(prediction.edge, 4),
            size_usd=size,
        )
        return SizingDecision(approved=True, size_usd=size, reason="All checks passed")
