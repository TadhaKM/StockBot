---
name: execute
description: Place a paper or live trade on a prediction market
trigger: /execute
---

# /execute

Submit an order through the appropriate executor.

## Usage

```
/execute --market-id <id> --outcome yes --size 250 --price 0.55
```

## Steps

### Paper mode (default)

```bash
cd predict-market-bot && python -c "
import asyncio, uuid
from src.execution.paper import PaperExecutor
from src.models import Order, OrderSide

async def main():
    order = Order(
        id=str(uuid.uuid4()),
        market_id='poly-stub-001',
        platform='polymarket',
        side=OrderSide.BUY,
        outcome='yes',
        contracts=100,
        limit_price=0.55,
    )
    executor = PaperExecutor()
    trade = await executor.submit(order)
    print('Filled:', trade.order.status)
    print('Price :', trade.order.fill_price)

asyncio.run(main())
"
```

### Pre-live checklist

- [ ] `TRADING_MODE=live` set in .env
- [ ] API credentials validated (non-empty, correct permissions)
- [ ] `python scripts/validate_risk.py` passes all checks
- [ ] Bankroll is correctly set in RiskManager
- [ ] Start with minimum contract size to verify connectivity
- [ ] Monitor first 3 orders manually before full automation
