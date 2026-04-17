# Skill: compound

Run a full bot cycle end-to-end: scan → filter → research → predict → risk → execute → learn.

## Single cycle
```bash
cd pmbot
python -m src.main
```

## Scheduled loop (every N minutes, default 15)
```bash
python -m src.main --loop
```

## Override config at runtime
```bash
python -m src.main --config config/staging.yaml
```

## Environment variable overrides
All config keys can be overridden with `PMBOT__SECTION__KEY` env vars:
```bash
PMBOT__BOT__TRADING_MODE=live \
PMBOT__RISK__BANKROLL_USD=5000 \
python -m src.main
```

## Check config before running
```bash
python scripts/validate_config.py
```

## Full pipeline checklist
- [ ] `config/secrets.yaml` created from `config/secrets.yaml.example`
- [ ] NewsAPI key set (for research)
- [ ] Polymarket/Kalshi API keys set (for live execution)
- [ ] `python scripts/validate_config.py` passes
- [ ] `pytest tests/` passes
- [ ] First run with paper trading: `python -m src.main`
- [ ] Review `data/trades/` JSONL output
