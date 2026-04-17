"""News fetching client."""
from __future__ import annotations

import httpx

from src.config import settings
from src.utils import get_logger

logger = get_logger(__name__)


class NewsClient:
    """Thin wrapper around a news API to pull relevant headlines."""

    def __init__(self) -> None:
        self.api_key = settings.news_api_key
        self.base_url = "https://newsapi.org/v2"

    async def search(self, query: str, max_results: int = 10) -> list[dict]:
        """
        Search for news articles relevant to a market question.

        TODO: Add more sources (GDELT, MediaStack, Bing News).
        TODO: Cache responses to avoid redundant API calls.
        """
        if not self.api_key:
            logger.warning("news.no_api_key", msg="Returning empty news results.")
            return []

        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/everything",
                    params={
                        "q": query,
                        "sortBy": "publishedAt",
                        "pageSize": max_results,
                        "apiKey": self.api_key,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("articles", [])
            except httpx.HTTPError as exc:
                logger.error("news.fetch_error", query=query, error=str(exc))
                return []
