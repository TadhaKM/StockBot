# Skill: scan

Scan Polymarket and Kalshi for open markets and surface the most tradeable opportunities.

## When to use
- You want a snapshot of live markets matching your filter criteria
- You are debugging scanner connectivity or stub data
- You want to confirm the bot is receiving market data before a full cycle

## How to invoke
```
python -m src.main          # runs a full cycle (scan is step 1)
```
Or call the scanner directly in a REPL:
```python
import asyncio
from src.scanner.polymarket import PolymarketScanner
markets = asyncio.run(PolymarketScanner().scan())
for m in markets:
    print(m.id, m.title, m.yes_price)
```

## Output fields (Market)
| Field | Description |
|-------|-------------|
| id | Platform-specific market identifier |
| title | Human-readable question |
| platform | `polymarket` or `kalshi` |
| yes_price | Current YES probability (0–1) |
| close_time | UTC datetime the market resolves |
| volume_usd | Total traded volume |
| category | Topic category (politics, economics, …) |

## Config knobs
```yaml
scanner:
  max_markets_per_platform: 50
  min_volume_usd: 10000
```
