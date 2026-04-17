"""Kalshi market scanner."""
from __future__ import annotations

import httpx

from src.config import settings
from src.models import Market, MarketOutcome, Platform
from src.utils import get_logger
from .base import BaseScanner

logger = get_logger(__name__)

_KALSHI_MARKETS_ENDPOINT = "/markets"


class KalshiScanner(BaseScanner):
    platform_name = "kalshi"

    def __init__(self) -> None:
        self.base_url = settings.kalshi_effective_url

    async def fetch_markets(self) -> list[Market]:
        """
        Fetch active markets from Kalshi REST API.

        TODO: Implement real Kalshi auth (HMAC-SHA256 signature).
        TODO: Paginate using cursor field in response.
        TODO: Filter by series_ticker, category, status="open".
        """
        if not settings.kalshi_api_key:
            logger.warning("kalshi.no_credentials", msg="Returning stub markets (paper mode).")
            return _stub_markets()

        async with httpx.AsyncClient(base_url=self.base_url, timeout=10) as client:
            try:
                # TODO: Add real Kalshi HMAC auth headers
                resp = await client.get(
                    _KALSHI_MARKETS_ENDPOINT,
                    params={"status": "open", "limit": 200},
                    headers={"Authorization": f"Bearer {settings.kalshi_api_key}"},
                )
                resp.raise_for_status()
                raw = resp.json()
                return _parse_kalshi_response(raw)
            except httpx.HTTPError as exc:
                logger.error("kalshi.fetch_error", error=str(exc))
                return []


def _parse_kalshi_response(raw: dict) -> list[Market]:
    """
    TODO: Implement real Kalshi response parsing.
    Kalshi markets have yes_bid/yes_ask/no_bid/no_ask prices.
    Implied probability = (yes_bid + yes_ask) / 2.
    """
    markets: list[Market] = []
    for item in raw.get("markets", []):
        # TODO: Parse real fields from Kalshi market response
        pass
    return markets


def _stub_markets() -> list[Market]:
    return [
        Market(
            id="kalshi-stub-001",
            platform=Platform.KALSHI,
            question="Will US CPI be above 3% in June 2025?",
            category="economics",
            outcomes=[
                MarketOutcome(id="yes", name="YES", probability=0.33, price=0.33, volume=90_000),
                MarketOutcome(id="no", name="NO", probability=0.67, price=0.67, volume=90_000),
            ],
            volume_usd=180_000,
            liquidity_usd=40_000,
        ),
    ]
