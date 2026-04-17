"""Prediction output model."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Prediction(BaseModel):
    market_id: str
    our_probability: float = Field(ge=0.0, le=1.0)
    market_probability: float = Field(ge=0.0, le=1.0)
    edge: float = 0.0           # our_prob - market_prob (positive = YES edge)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    model_name: str = "baseline"
    rationale: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def model_post_init(self, __context: object) -> None:  # noqa: D102
        self.edge = self.our_probability - self.market_probability

    @property
    def has_edge(self) -> bool:
        return abs(self.edge) > 0.0

    @property
    def recommended_side(self) -> str:
        return "yes" if self.edge > 0 else "no"
