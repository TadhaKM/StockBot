"""Abstract base predictor."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.models import Market, Prediction
from src.research.researcher import ResearchResult


class BasePredictor(ABC):
    model_name: str = "base"

    @abstractmethod
    async def predict(self, market: Market, research: ResearchResult) -> Prediction:
        """Return a probability estimate for the YES outcome."""
        ...
