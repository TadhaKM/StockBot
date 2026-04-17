# predict-market-bot

A modular Python bot for trading on prediction markets (Polymarket, Kalshi).

**Safe by default: paper trading mode is on. No real money moves until you explicitly set `TRADING_MODE=live`.**

---

## Architecture

```
scan → research → predict → risk → execute → learn
```

| Module | Purpose |
|--------|---------|
| `scanners/` | Fetch and filter markets from each platform |
| `research/` | News search, base-rate lookup, LLM summarization |
| `prediction/` | Estimate probabilities; compute edge vs market |
| `risk/` | Kelly sizing, position limits, hard caps |
| `execution/` | Paper executor + placeholder live adapters |
| `learning/` | Record predictions, track calibration over time |

---

## Setup

### 1. Clone and install

```bash
git clone <repo>
cd predict-market-bot
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — API keys are optional in paper mode
```

### 3. Validate config

```bash
python scripts/validate_risk.py
```

### 4. Run (paper mode)

```bash
python -m src.main
```

### 5. Scheduled loop

```bash
python -m src.main --loop      # runs every 15 minutes
```

---

## Skills (Claude Code slash commands)

| Command | Description |
|---------|-------------|
| `/scan` | Scan platforms for tradeable markets |
| `/research` | Deep research a specific market question |
| `/predict` | Run prediction pipeline on a market |
| `/risk` | Size a trade and validate risk gates |
| `/execute` | Place a paper or live order |
| `/compound` | Run the full end-to-end cycle |

---

## Scripts

| Script | Usage |
|--------|-------|
| `scripts/kelly_size.py` | Compute Kelly sizing for given edge |
| `scripts/validate_risk.py` | Sanity-check risk config before going live |
| `scripts/backtest.py` | Review historical paper trade P&L |
| `scripts/nightly_review.py` | Daily summary (run via cron) |

---

## Tests

```bash
pytest tests/ -v
```

---

## Going live

1. Set `TRADING_MODE=live` in `.env`
2. Add real API credentials for Polymarket and/or Kalshi
3. Run `python scripts/validate_risk.py` — all checks must pass
4. Implement the live executors in `src/execution/polymarket_executor.py` and `kalshi_executor.py`
5. Start with minimum position sizes and monitor manually for the first week

---

## Data layout

```
data/
  raw/            raw API responses (optional caching)
  processed/      cleaned datasets for backtesting
  logs/           bot.log, predictions.jsonl
  paper_trades/   YYYY-MM-DD.jsonl trade records
```

---

## References

- [`references/formulas.md`](references/formulas.md) — Kelly, Brier score, edge calculations
- [`references/platforms.md`](references/platforms.md) — API docs and platform comparison
- [`references/failure_log.md`](references/failure_log.md) — Post-mortems on bad trades

---

## Disclaimer

This is experimental software. Prediction market trading carries significant financial risk.
Always paper trade first. Never risk money you cannot afford to lose.
