# Skill: execute

Submit a trade via the paper executor (or live executor when ready).

## When to use
- Reviewing paper trade logs
- Verifying order fields before going live
- Switching from paper to live execution

## Paper trade log
Paper trades are appended to `data/trades/YYYY-MM-DD.jsonl`. Each line is a JSON object:
```json
{
  "trade_id": "uuid",
  "market_id": "polymarket-abc",
  "platform": "polymarket",
  "side": "YES",
  "size_usd": 47.32,
  "limit_price": 0.55,
  "status": "filled",
  "filled_at": "2025-01-15T12:00:00"
}
```

## Switching to live
1. Set `PMBOT__BOT__TRADING_MODE=live` in your environment or `config/secrets.yaml`
2. Implement `src/execution/polymarket.py` and `src/execution/kalshi.py`
3. Swap `PaperExecutor` for `PolymarketExecutor`/`KalshiExecutor` in `src/orchestrator/bot.py`

## Backtest CLI
```bash
python scripts/backtest.py --trades-dir data/trades
```
