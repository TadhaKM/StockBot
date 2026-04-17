"""
Quality gate applied to scanned markets before they enter the prediction pipeline.
Config-driven: all thresholds live in config/default.yaml under `filter:`.
"""
from __future__ import annotations

from src.config import cfg
from src.logging_setup import get_logger
from src.scanner.base import Market

logger = get_logger(__name__)


class MarketFilter:
    """Applies sequential quality gates to a list of markets."""

    def run(self, markets: list[Market]) -> list[Market]:
        fc = cfg.filter
        results: list[Market] = []
        rejected: dict[str, int] = {}

        for m in markets:
            reason = self._reject_reason(m, fc)
            if reason:
                rejected[reason] = rejected.get(reason, 0) + 1
            else:
                results.append(m)

        logger.info(
            "filter.complete",
            before=len(markets),
            after=len(results),
            rejected=rejected,
        )
        return results

    @staticmethod
    def _reject_reason(market: Market, fc) -> str | None:
        # Probability extremes (near-certain outcomes)
        if market.yes_probability < fc.min_market_probability:
            return "prob_too_low"
        if market.yes_probability > fc.max_market_probability:
            return "prob_too_high"

        # Category allowlist / blocklist
        if fc.required_categories and market.category not in fc.required_categories:
            return "category_not_required"
        if market.category in fc.blocked_categories:
            return "category_blocked"

        return None
