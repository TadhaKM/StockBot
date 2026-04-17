# Skill: research

Gather news headlines and compute a sentiment signal for a given market.

## When to use
- Understanding why the bot assigned a particular sentiment score
- Debugging missing or stale news data
- Manually checking research output before placing a trade

## How to invoke
```python
import asyncio
from src.research.researcher import MarketResearcher
from src.scanner.base import Market
from datetime import datetime, timezone, timedelta

market = Market(
    id="test",
    title="Will the Fed cut rates in June?",
    platform="polymarket",
    yes_price=0.55,
    close_time=datetime.now(timezone.utc) + timedelta(days=30),
    volume_usd=500_000,
    category="economics",
)
result = asyncio.run(MarketResearcher().research(market))
print(result.sentiment_score, result.summary)
```

## Output fields (ResearchResult)
| Field | Description |
|-------|-------------|
| market_id | Market being researched |
| headlines | List of recent news headlines |
| sentiment_score | Float in [-1, 1]; positive = bullish |
| summary | One-sentence synthesis |

## Config knobs
```yaml
# No dedicated research section yet — uses NewsAPI key from secrets.yaml
```
