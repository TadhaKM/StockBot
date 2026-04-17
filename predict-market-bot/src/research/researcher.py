"""Orchestrates research for a given market."""
from __future__ import annotations

from src.models import Market
from src.utils import get_logger
from .news import NewsClient

logger = get_logger(__name__)


class ResearchResult:
    def __init__(self, market_id: str) -> None:
        self.market_id = market_id
        self.articles: list[dict] = []
        self.summary: str = ""
        self.base_rate: float | None = None   # historical base rate if known
        self.key_factors: list[str] = []


class MarketResearcher:
    """
    Gathers evidence for a market question.

    Current pipeline:
      1. Keyword search via NewsClient
      2. (TODO) LLM summarization
      3. (TODO) Base-rate lookup from historical data
    """

    def __init__(self) -> None:
        self.news = NewsClient()

    async def research(self, market: Market) -> ResearchResult:
        result = ResearchResult(market_id=market.id)

        # Step 1: News
        articles = await self.news.search(market.question, max_results=5)
        result.articles = articles
        logger.info("research.news", market_id=market.id, articles=len(articles))

        # TODO: Step 2 — LLM summarization
        # prompt = build_research_prompt(market, articles)
        # result.summary = await llm_client.complete(prompt)

        # TODO: Step 3 — Base-rate lookup
        # result.base_rate = base_rate_db.lookup(market.category, market.question)

        # TODO: Step 4 — Extract key factors from summary
        # result.key_factors = extract_key_factors(result.summary)

        return result
