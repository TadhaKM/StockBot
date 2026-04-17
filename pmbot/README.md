# pmbot — Prediction Market Trading Bot

A production-style bot for trading on Polymarket and Kalshi.  
Paper trading by default. Structured logging. YAML config with env-var overrides.

## Quick start

```bash
cd pmbot
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp config/secrets.yaml.example config/secrets.yaml
# Edit config/secrets.yaml with your API keys

python scripts/validate_config.py   # verify config
pytest tests/                       # run tests

python -m src.main                  # single cycle (paper trading)
python -m src.main --loop           # every 15 minutes
```

## Project layout

```
pmbot/
├── config/
│   ├── default.yaml            # all non-secret defaults
│   └── secrets.yaml.example    # copy → secrets.yaml, fill in keys
├── src/
│   ├── scanner/        # Polymarket + Kalshi market scanners
│   ├── filter/         # probability + category gates
│   ├── research/       # news headline sentiment
│   ├── prediction/     # baseline predictor (sentiment nudge)
│   ├── risk/           # Kelly criterion + risk gates
│   ├── execution/      # paper executor (live stubs)
│   ├── learning/       # prediction log + performance tracker
│   ├── orchestrator/   # Bot class wiring everything together
│   ├── config.py       # YAML loader + pydantic Config model
│   ├── logging_setup.py
│   └── main.py         # typer CLI entry point
├── scripts/
│   ├── kelly_size.py       # compute stake for a given edge
│   ├── validate_config.py  # pre-flight config check
│   └── backtest.py         # summarize paper trade logs
├── skills/             # Claude Code skill docs
├── tests/
│   ├── test_kelly.py
│   ├── test_filter.py
│   └── test_prediction.py
└── data/
    ├── logs/           # prediction JSONL logs
    └── trades/         # paper trade JSONL logs
```

## Configuration

Edit `config/default.yaml` or override with environment variables:

```bash
PMBOT__BOT__TRADING_MODE=live
PMBOT__RISK__BANKROLL_USD=5000
PMBOT__RISK__MAX_BANKROLL_FRACTION=0.03
```

## Pipeline

```
scan → filter → research → predict → risk → execute → learn
```

1. **Scan** — fetch open markets from Polymarket and Kalshi
2. **Filter** — drop extremes (>95% / <5%), excluded categories
3. **Research** — pull recent news, compute sentiment score
4. **Predict** — nudge market price by sentiment → our probability
5. **Risk** — Kelly sizing, max position count, duplicate check
6. **Execute** — submit to paper executor (JSONL log) or live API
7. **Learn** — record prediction; call `tracker.resolve()` at settlement

## Going live

1. Set `trading_mode: live` in config or via env var
2. Implement `src/execution/polymarket.py` and `src/execution/kalshi.py`
3. Swap executors in `src/orchestrator/bot.py`
4. Fund accounts and set API keys in `config/secrets.yaml`
