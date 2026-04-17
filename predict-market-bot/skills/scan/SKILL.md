---
name: scan
description: Scan Polymarket and Kalshi for tradeable markets matching configured filters
trigger: /scan
---

# /scan

Run the market scanner against all configured platforms and print a ranked list of markets sorted by volume.

## Steps

1. Run the scanner:

```bash
cd predict-market-bot && python -c "
import asyncio
from src.scanners.polymarket import PolymarketScanner
from src.scanners.kalshi import KalshiScanner

async def main():
    markets = []
    for s in [PolymarketScanner(), KalshiScanner()]:
        markets.extend(await s.scan())
    markets.sort(key=lambda m: m.volume_usd, reverse=True)
    for m in markets[:20]:
        prob = m.yes_probability
        print(f'[{m.platform.value:12}] vol=${m.volume_usd:,.0f}  p={prob:.2f}  {m.question[:70]}')

asyncio.run(main())
"
```

2. Review the output. Flag any market where:
   - Volume > $500k (liquid enough to trade)
   - YES probability is between 0.15 and 0.85 (not already resolved)
   - `days_to_close` < 30 (time-sensitive signal)

3. Pass interesting markets to `/research` for deeper analysis.
