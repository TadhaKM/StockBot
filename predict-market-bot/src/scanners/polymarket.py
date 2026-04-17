"""Polymarket market scanner."""
from __future__ import annotations

import httpx

from src.config import settings
from src.models import Market, MarketOutcome, Platform
from src.utils import get_logger
from .base import BaseScanner

logger = get_logger(__name__)

# TODO: Replace stub with real Polymarket CLOB API pagination
_POLYMARKET_MARKETS_ENDPOINT = "/markets"


class PolymarketScanner(BaseScanner):
    platform_name = "polymarket"

    def __init__(self) -> None:
        self.base_url = settings.polymarket_base_url

    async def fetch_markets(self) -> list[Market]:
        """
        Fetch active markets from Polymarket CLOB API.

        TODO: Implement real pagination — API returns cursor-based pages.
        TODO: Add authentication header (L1/L2 CLOB auth).
        TODO: Handle rate limits (429) with exponential backoff via tenacity.
        """
        if not settings.polymarket_api_key:
            logger.warning("polymarket.no_credentials", msg="Returning stub markets (paper mode).")
            return _stub_markets()

        # TODO: Replace with real API call
        async with httpx.AsyncClient(base_url=self.base_url, timeout=10) as client:
            try:
                resp = await client.get(
                    _POLYMARKET_MARKETS_ENDPOINT,
                    params={"active": True, "closed": False},
                    headers={"Authorization": f"Bearer {settings.polymarket_api_key}"},
                )
                resp.raise_for_status()
                raw = resp.json()
                return _parse_polymarket_response(raw)
            except httpx.HTTPError as exc:
                logger.error("polymarket.fetch_error", error=str(exc))
                return []


def _parse_polymarket_response(raw: dict) -> list[Market]:
    """
    TODO: Implement real Polymarket response parsing.
    The CLOB API returns markets with tokens representing YES/NO.
    """
    markets: list[Market] = []
    for item in raw.get("data", []):
        # TODO: Parse real fields from Polymarket CLOB response
        pass
    return markets


def _stub_markets() -> list[Market]:
    """Return synthetic markets for paper trading / development."""
    return [
        Market(
            id="poly-stub-001",
            platform=Platform.POLYMARKET,
            question="Will the Fed cut rates in Q3 2025?",
            category="economics",
            outcomes=[
                MarketOutcome(id="yes", name="YES", probability=0.62, price=0.62, volume=250_000),
                MarketOutcome(id="no", name="NO", probability=0.38, price=0.38, volume=250_000),
            ],
            volume_usd=500_000,
            liquidity_usd=80_000,
        ),
        Market(
            id="poly-stub-002",
            platform=Platform.POLYMARKET,
            question="Will Bitcoin exceed $100k by end of 2025?",
            category="crypto",
            outcomes=[
                MarketOutcome(id="yes", name="YES", probability=0.45, price=0.45, volume=1_200_000),
                MarketOutcome(id="no", name="NO", probability=0.55, price=0.55, volume=1_200_000),
            ],
            volume_usd=2_400_000,
            liquidity_usd=350_000,
        ),
    ]
