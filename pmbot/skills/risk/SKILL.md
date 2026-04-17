# Skill: risk

Evaluate a prediction through the risk manager and compute Kelly-sized stake.

## When to use
- Verifying which risk gates are rejecting trades
- Tuning bankroll fraction, max positions, or minimum edge
- Computing Kelly stake for a hypothetical trade

## Kelly size CLI
```bash
python scripts/kelly_size.py \
  --our-prob 0.62 \
  --market-prob 0.50 \
  --bankroll 1000 \
  --fraction 0.25 \
  --max-pct 0.05
```

## Risk gates (in order)
1. **Edge gate** — `abs(edge) < min_edge` → skip
2. **Position count** — open positions ≥ max_open_positions → skip
3. **Duplicate** — market already in open set → skip
4. **Confidence** — `abs(edge) < min_confidence` → skip
5. **Kelly sizing** — computed from bankroll × Kelly fraction, capped at max_fraction

## Config knobs
```yaml
risk:
  bankroll_usd: 1000.0
  max_bankroll_fraction: 0.05
  max_open_positions: 10
  min_edge: 0.05
  kelly_fraction: 0.25
  min_confidence: 0.03
```
