"""Polymarket scanner — returns stub markets until API is wired in."""
from __future__ import annotations

from datetime import datetime, timedelta

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
            logger.warning("polymarket.no_credentials", fallback="stubs")
            return _stubs()

        base_url = cfg.platforms.polymarket.base_url
        async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
            try:
                resp = await client.get(
                    "/markets",
                    params={"active": True, "closed": False},
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
                # TODO: parse real response shape
                return []
            except httpx.HTTPError as exc:
                logger.error("polymarket.fetch_error", error=str(exc))
                return []


def _stubs() -> list[Market]:
    return [
        Market(
            id="poly-001",
            platform="polymarket",
            question="Will the Fed cut rates before July 2025?",
            category="economics",
            yes_probability=0.62,
            volume_usd=500_000,
            liquidity_usd=80_000,
            close_time=datetime.utcnow() + timedelta(days=45),
        ),
        Market(
            id="poly-002",
            platform="polymarket",
            question="Will Bitcoin exceed $100k by end of 2025?",
            category="crypto",
            yes_probability=0.45,
            volume_usd=2_400_000,
            liquidity_usd=350_000,
            close_time=datetime.utcnow() + timedelta(days=180),
        ),
    ]
