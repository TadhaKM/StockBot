"""Abstract predictor interface and result types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.research.researcher import ResearchResult
from src.scanner.base import Market


@dataclass
class PredictionResult:
    """Raw output from a predictor -- no rules applied yet."""
    market_id: str
    p_model: float          # model's estimated probability (0-1)
    p_market: float         # market mid-price at prediction time
    confidence: float       # model's self-assessed confidence (0-1)
    model_name: str
    rationale: str = ""

    @property
    def edge(self) -> float:
        return self.p_model - self.p_market

    @property
    def recommended_side(self) -> str:
        return "yes" if self.edge >= 0 else "no"


class BasePredictor(ABC):
    name: str = "base"

    @abstractmethod
    async def predict(self, market: Market, research: ResearchResult) -> PredictionResult:
        ...
