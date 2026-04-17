"""Kalshi scanner — returns stub markets until API is wired in."""
from __future__ import annotations

from datetime import datetime, timedelta

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
        TODO: Map yes_bid/yes_ask midpoint to yes_probability.
        """
        secrets = cfg.secrets.get("kalshi", {})
        api_key = secrets.get("api_key", "")

        if not api_key:
            logger.warning("kalshi.no_credentials", fallback="stubs")
            return _stubs()

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


def _stubs() -> list[Market]:
    return [
        Market(
            id="kalshi-001",
            platform="kalshi",
            question="Will US CPI be above 3% in June 2025?",
            category="economics",
            yes_probability=0.33,
            volume_usd=180_000,
            liquidity_usd=40_000,
            close_time=datetime.utcnow() + timedelta(days=30),
        ),
    ]
