"""
Market filter: applies trading_rules.yaml quality gates, ranks survivors,
and saves the full scan+filter result to data/logs/scanner_output.json.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.config.rules import load_rules, validate_market_conditions, TradingRules
from src.logging_setup import get_logger
from src.scanner.base import Market

logger = get_logger(__name__)

_OUTPUT_PATH = Path("data/logs/scanner_output.json")


@dataclass
class ScoredMarket:
    market: Market
    score: float


def ranking_score(market: Market, rules: TradingRules) -> float:
    """
    Composite quality score in [0, 100].

    Weights:
        35% volume       — higher traded volume = more reliable price
        30% tightness    — tighter spread = cheaper to trade
        20% depth        — deeper orderbook = less slippage
        15% urgency      — closer expiry = more actionable
    """
    mr = rules.market

    # Volume: log-scale relative to threshold (1.0 = at threshold, higher = better)
    vol_norm = min(math.log1p(market.volume_usd) / math.log1p(mr.min_volume * 100), 1.0)

    # Spread tightness: 1.0 when spread=0, 0.0 when spread >= max_spread
    tight_norm = max(1.0 - market.spread / mr.max_spread, 0.0) if mr.max_spread > 0 else 1.0

    # Orderbook depth: log-scale relative to threshold
    depth_norm = min(
        math.log1p(market.orderbook_depth) / math.log1p(mr.min_orderbook_depth * 50), 1.0
    )

    # Urgency: closer to expiry = higher, capped at 1.0 when <=1 day out
    dtc = market.days_to_close
    if dtc is not None and mr.max_days_to_expiry > 0:
        urgency_norm = max(1.0 - dtc / mr.max_days_to_expiry, 0.0)
    else:
        urgency_norm = 0.5  # unknown expiry gets neutral urgency

    return round(
        (0.35 * vol_norm + 0.30 * tight_norm + 0.20 * depth_norm + 0.15 * urgency_norm) * 100,
        2,
    )


class MarketFilter:
    """Applies trading rules, ranks survivors, saves output."""

    def __init__(self, rules: TradingRules | None = None) -> None:
        self.rules = rules or load_rules()

    def run(self, markets: list[Market]) -> list[ScoredMarket]:
        passed: list[ScoredMarket] = []
        rejected: list[dict] = []

        for m in markets:
            result = validate_market_conditions(m, self.rules)
            if result.passed:
                score = ranking_score(m, self.rules)
                passed.append(ScoredMarket(market=m, score=score))
            else:
                rejected.append({"id": m.id, "title": m.title, "failures": result.failures})

        # Sort by ranking score descending — best opportunities first
        passed.sort(key=lambda sm: sm.score, reverse=True)

        logger.info(
            "filter.complete",
            scanned=len(markets),
            passed=len(passed),
            rejected=len(rejected),
        )
        for rej in rejected:
            logger.info("filter.rejected", **rej)

        self._save_output(passed, rejected)
        return passed

    @staticmethod
    def _save_output(passed: list[ScoredMarket], rejected: list[dict]) -> None:
        _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_scanned": len(passed) + len(rejected),
                "passed": len(passed),
                "rejected": len(rejected),
            },
            "markets": [
                {
                    "id": sm.market.id,
                    "title": sm.market.title,
                    "platform": sm.market.platform,
                    "category": sm.market.category,
                    "bid": sm.market.bid,
                    "ask": sm.market.ask,
                    "spread": round(sm.market.spread, 4),
                    "mid_price": round(sm.market.mid_price, 4),
                    "volume_usd": sm.market.volume_usd,
                    "orderbook_depth": sm.market.orderbook_depth,
                    "days_to_close": round(sm.market.days_to_close, 1)
                    if sm.market.days_to_close is not None
                    else None,
                    "ranking_score": sm.score,
                    "status": "passed",
                }
                for sm in passed
            ]
            + [
                {**r, "ranking_score": None, "status": "rejected"}
                for r in rejected
            ],
        }
        _OUTPUT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")
        logger.info("filter.saved", path=str(_OUTPUT_PATH))
