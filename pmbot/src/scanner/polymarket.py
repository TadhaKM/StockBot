"""Polymarket scanner — returns mock markets until API is wired in."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from src.config import cfg
from src.logging_setup import get_logger
from .base import BaseScanner, Market

logger = get_logger(__name__)


class PolymarketScanner(BaseScanner):
    platform = "polymarket"

    async def fetch_all(self) -> list[Market]:
        """
        TODO: Implement real Polymarket CLOB API pagination.
        TODO: Add L1/L2 authentication headers.
        TODO: Handle 429 rate limits with tenacity retry.
        """
        secrets = cfg.secrets.get("polymarket", {})
        api_key = secrets.get("api_key", "")

        if not api_key:
            logger.warning("polymarket.no_credentials", fallback="mock")
            return _mock_markets()

        base_url = cfg.platforms.polymarket.base_url
        async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
            try:
                resp = await client.get(
                    "/markets",
                    params={"active": True, "closed": False},
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
                # TODO: parse real response shape. Until then we return
                # mock data so the rest of the pipeline has something to
                # chew on -- empty results would silently starve it.
                logger.warning(
                    "polymarket.parse_todo",
                    fallback="mock",
                    reason="response parsing not implemented",
                )
                return _mock_markets()
            except httpx.HTTPError as exc:
                logger.error("polymarket.fetch_error", error=str(exc), fallback="mock")
                return _mock_markets()


def _mock_markets() -> list[Market]:
    """Diverse mock data — some pass rules, some fail on purpose."""
    return [
        Market(
            id="poly-001",
            title="Will the Fed cut rates before July 2026?",
            platform="polymarket",
            category="economics",
            bid=0.60,
            ask=0.62,
            volume_usd=520_000,
            orderbook_depth=14_000,
            close_time=datetime.now(timezone.utc) + timedelta(days=22),
        ),
        Market(
            id="poly-002",
            title="Will Bitcoin exceed $150k by end of 2026?",
            platform="polymarket",
            category="crypto",
            bid=0.43,
            ask=0.47,
            volume_usd=2_400_000,
            orderbook_depth=45_000,
            close_time=datetime.now(timezone.utc) + timedelta(days=180),
        ),
        Market(
            id="poly-003",
            title="Will US GDP growth exceed 3% in Q2 2026?",
            platform="polymarket",
            category="economics",
            bid=0.34,
            ask=0.36,
            volume_usd=310_000,
            orderbook_depth=8_500,
            close_time=datetime.now(timezone.utc) + timedelta(days=18),
        ),
        Market(
            id="poly-004",
            title="Will candidate X win the 2026 midterms?",
            platform="polymarket",
            category="politics",
            bid=0.70,
            ask=0.72,
            volume_usd=1_100_000,
            orderbook_depth=22_000,
            close_time=datetime.now(timezone.utc) + timedelta(days=12),
        ),
        # ── Should fail: low volume ──
        Market(
            id="poly-005",
            title="Will it snow in Miami in June?",
            platform="polymarket",
            category="weather",
            bid=0.01,
            ask=0.03,
            volume_usd=120,
            orderbook_depth=30,
            close_time=datetime.now(timezone.utc) + timedelta(days=5),
        ),
        # ── Should fail: wide spread ──
        Market(
            id="poly-006",
            title="Will Mars colony be announced by 2027?",
            platform="polymarket",
            category="science",
            bid=0.05,
            ask=0.15,
            volume_usd=8_000,
            orderbook_depth=200,
            close_time=datetime.now(timezone.utc) + timedelta(days=25),
        ),
    ]
