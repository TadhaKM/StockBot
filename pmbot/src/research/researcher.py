"""
Research pipeline: gathers evidence for a market question.

Current implementation fetches news headlines.
TODO: Add LLM summarization, base-rate lookup, and source scoring.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from src.config import cfg
from src.logging_setup import get_logger
from src.scanner.base import Market

logger = get_logger(__name__)


@dataclass
class ResearchResult:
    market_id: str
    articles: list[dict] = field(default_factory=list)
    summary: str = ""
    base_rate: float | None = None
    key_factors: list[str] = field(default_factory=list)


class MarketResearcher:

    async def research(self, market: Market) -> ResearchResult:
        result = ResearchResult(market_id=market.id)

        news_key = cfg.secrets.get("research", {}).get("news_api_key", "")
        if news_key:
            result.articles = await self._fetch_news(market.question, news_key)
        else:
            logger.warning("research.no_news_key", market_id=market.id)

        logger.info("research.done", market_id=market.id, articles=len(result.articles))

        # TODO: Step 2 — LLM summarization
        # result.summary = await llm.summarize(market.question, result.articles)

        # TODO: Step 3 — base-rate lookup from historical data store

        return result

    @staticmethod
    async def _fetch_news(query: str, api_key: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(
                    "https://newsapi.org/v2/everything",
                    params={"q": query, "sortBy": "publishedAt", "pageSize": 5, "apiKey": api_key},
                )
                resp.raise_for_status()
                return resp.json().get("articles", [])
            except httpx.HTTPError as exc:
                logger.error("research.news_error", error=str(exc))
                return []
