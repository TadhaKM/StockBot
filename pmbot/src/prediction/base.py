"""Abstract predictor interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.research.researcher import ResearchResult
from src.scanner.base import Market


@dataclass
class PredictionResult:
    market_id: str
    our_probability: float
    market_probability: float
    confidence: float
    model_name: str
    rationale: str = ""

    @property
    def edge(self) -> float:
        return self.our_probability - self.market_probability

    @property
    def has_edge(self) -> bool:
        return abs(self.edge) > 0.0

    @property
    def recommended_side(self) -> str:
        return "yes" if self.edge >= 0 else "no"


class BasePredictor(ABC):
    name: str = "base"

    @abstractmethod
    async def predict(self, market: Market, research: ResearchResult) -> PredictionResult:
        ...
