---
name: compound
description: Run the full scan → research → predict → risk → execute pipeline end to end
trigger: /compound
---

# /compound

Run a complete automated cycle from market discovery to trade execution.

## Usage

```
/compound                    # single run, paper mode
/compound --loop             # run every 15 minutes
```

## Steps

### Single cycle

```bash
cd predict-market-bot && python -m src.main
```

### Scheduled loop (15-minute interval)

```bash
cd predict-market-bot && python -m src.main --loop
```

### What happens each cycle

1. **Scan** — fetches markets from Polymarket and Kalshi, filters by volume/liquidity
2. **Research** — pulls recent news articles for each market
3. **Predict** — runs baseline predictor, computes edge vs market price
4. **Risk** — evaluates edge threshold, position limits, Kelly sizing
5. **Execute** — submits paper (or live) orders for approved trades
6. **Track** — records prediction + trade to `data/paper_trades/` and `data/logs/predictions.jsonl`

### Monitoring

- Watch `data/logs/bot.log` for structured events
- Review `data/paper_trades/<date>.jsonl` for trade records
- Run `python scripts/nightly_review.py` for daily summary
- Run `python scripts/backtest.py` for historical P&L

### Escalation

If more than 3 consecutive cycles produce zero trades, check:
1. Are stubs returning markets? (`/scan`)
2. Is the edge threshold too high? (`MIN_EDGE_THRESHOLD` in .env)
3. Are API credentials valid?
