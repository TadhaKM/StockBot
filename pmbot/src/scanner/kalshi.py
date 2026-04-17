"""Kalshi scanner — returns mock markets until API is wired in."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from src.config import cfg
from src.logging_setup import get_logger
from .base import BaseScanner, Market

logger = get_logger(__name__)


class KalshiScanner(BaseScanner):
    platform = "kalshi"

    async def fetch_all(self) -> list[Market]:
        """
        TODO: Implement HMAC-SHA256 auth for Kalshi API.
        TODO: Paginate using cursor field.
        """
        secrets = cfg.secrets.get("kalshi", {})
        api_key = secrets.get("api_key", "")

        if not api_key:
            logger.warning("kalshi.no_credentials", fallback="mock")
            return _mock_markets()

        base_url = cfg.platforms.kalshi.demo_url if cfg.bot.is_paper else cfg.platforms.kalshi.base_url
        async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
            try:
                resp = await client.get(
                    "/markets",
                    params={"status": "open", "limit": 200},
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
                # TODO: parse real response
                return []
            except httpx.HTTPError as exc:
                logger.error("kalshi.fetch_error", error=str(exc))
                return []


def _mock_markets() -> list[Market]:
    return [
        Market(
            id="kalshi-001",
            title="Will US CPI be above 3% in June 2026?",
            platform="kalshi",
            category="economics",
            bid=0.31,
            ask=0.34,
            volume_usd=185_000,
            orderbook_depth=6_200,
            close_time=datetime.now(timezone.utc) + timedelta(days=28),
        ),
        Market(
            id="kalshi-002",
            title="Will unemployment rise above 5% by Q3 2026?",
            platform="kalshi",
            category="economics",
            bid=0.18,
            ask=0.20,
            volume_usd=95_000,
            orderbook_depth=3_800,
            close_time=datetime.now(timezone.utc) + timedelta(days=15),
        ),
        # ── Should fail: thin orderbook ──
        Market(
            id="kalshi-003",
            title="Will there be a Category 5 hurricane in 2026?",
            platform="kalshi",
            category="weather",
            bid=0.40,
            ask=0.42,
            volume_usd=2_000,
            orderbook_depth=50,
            close_time=datetime.now(timezone.utc) + timedelta(days=20),
        ),
    ]
