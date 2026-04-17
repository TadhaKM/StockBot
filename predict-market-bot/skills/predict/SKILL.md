---
name: predict
description: Generate a probability estimate for a market
trigger: /predict
---

# /predict

Run the prediction pipeline on a specific market and return our estimated probability.

## Usage

```
/predict <market_id>
```

## Steps

1. Load market data from scanner output or paste raw market JSON.

2. Run baseline predictor:

```bash
cd predict-market-bot && python -c "
import asyncio
from src.models import Market, MarketOutcome, Platform
from src.prediction.baseline import BaselinePredictor
from src.research.researcher import MarketResearcher, ResearchResult

async def main():
    # Replace with real market data
    market = Market(
        id='test-001',
        platform=Platform.POLYMARKET,
        question='YOUR QUESTION HERE',
        outcomes=[
            MarketOutcome(id='yes', name='YES', probability=0.55, price=0.55, volume=100000),
            MarketOutcome(id='no',  name='NO',  probability=0.45, price=0.45, volume=100000),
        ],
        volume_usd=200000,
        liquidity_usd=50000,
    )
    research = ResearchResult(market_id=market.id)
    pred = await BaselinePredictor().predict(market, research)
    print(f'Our prob  : {pred.our_probability:.1%}')
    print(f'Market    : {pred.market_probability:.1%}')
    print(f'Edge      : {pred.edge:+.1%}')
    print(f'Side      : {pred.recommended_side}')
    print(f'Rationale : {pred.rationale}')

asyncio.run(main())
"
```

3. Challenge the output:
   - Does the news sentiment make sense here?
   - Is there a base rate that anchors this differently?
   - Would you bet your own money at this edge?

4. If edge ≥ 5%, pass to `/risk` for sizing.
