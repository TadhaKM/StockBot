# Skill: predict

Run the baseline predictor to estimate our probability and compute edge vs market price.

## When to use
- Checking how the model prices a specific market
- Verifying edge computation and recommended side
- Swapping in a new predictor implementation

## How to invoke
```python
import asyncio
from src.prediction.baseline import BaselinePredictor
# (market and research from scan/research skills above)
pred = asyncio.run(BaselinePredictor().predict(market, research))
print(pred.our_probability, pred.edge, pred.recommended_side, pred.has_edge)
```

## Output fields (PredictionResult)
| Field | Description |
|-------|-------------|
| market_id | Market ID |
| our_probability | Model's estimated YES probability |
| market_probability | Market's current YES price |
| edge | our_probability − market_probability |
| recommended_side | `YES` or `NO` |
| has_edge | True if abs(edge) ≥ min_edge threshold |
| model_name | Identifier of predictor used |

## Extending the predictor
Subclass `BasePredictor` in `src/prediction/base.py` and implement `predict()`. Swap it into `src/orchestrator/bot.py`.
