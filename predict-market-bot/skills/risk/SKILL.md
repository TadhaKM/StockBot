---
name: risk
description: Size a trade and validate it passes all risk gates
trigger: /risk
---

# /risk

Given a prediction, compute position size and run all risk checks.

## Usage

```
/risk --prob 0.68 --market-price 0.55 --bankroll 10000
```

## Steps

1. Compute Kelly sizing:

```bash
cd predict-market-bot && python scripts/kelly_size.py --prob 0.68 --price 0.55 --bankroll 10000
```

2. Validate config:

```bash
cd predict-market-bot && python scripts/validate_risk.py
```

3. Check risk manager gates manually:

```bash
cd predict-market-bot && python -c "
from src.risk.manager import RiskManager
from src.models import Prediction

pred = Prediction(
    market_id='test-001',
    our_probability=0.68,
    market_probability=0.55,
    confidence=0.6,
)
rm = RiskManager(bankroll=10000)
d = rm.evaluate(pred)
print('Approved:', d.approved)
print('Size USD:', d.size_usd)
print('Reason  :', d.reason)
"
```

4. Rules of thumb:
   - Never exceed 5% of bankroll on a single trade
   - Require at least 3% edge before trading
   - Use quarter-Kelly unless back-tested calibration justifies more
   - Treat correlated markets (same event, different outcomes) as one position
