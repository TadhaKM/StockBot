# Formulas Reference

## Kelly Criterion (binary market)

```
b  = net odds = (1 - price) / price
f* = (p·b - q) / b   where q = 1 - p
   = (p - price) / (1 - price)
```

Use fractional Kelly: `f = f* × 0.25` (quarter-Kelly) to account for estimation error.

**Example**: p=0.65, price=0.55
```
b  = (1 - 0.55) / 0.55 = 0.818
f* = (0.65 × 0.818 - 0.35) / 0.818 = (0.532 - 0.35) / 0.818 = 0.222
f  = 0.222 × 0.25 = 0.056  → bet 5.6% of bankroll
```

---

## Edge

```
edge = our_probability - market_implied_probability
```

Only trade when `|edge| ≥ MIN_EDGE_THRESHOLD` (default 3%).

---

## Brier Score (calibration)

```
BS = (1/N) Σ (forecast_i - outcome_i)²
```

Lower is better. Perfect = 0. Uninformed (always 0.5) = 0.25.

---

## Log Loss

```
LL = -(1/N) Σ [y·log(p) + (1-y)·log(1-p)]
```

Lower is better. Use as primary calibration metric alongside Brier.

---

## Implied Probability from Price

For binary markets on Polymarket (USDC collateral):
```
p_yes = yes_token_price      (ranges 0–1, in USDC per share)
p_no  = 1 - p_yes            (approximately, ignoring spread)
```

For Kalshi (USD collateral):
```
p_yes = (yes_bid + yes_ask) / 2
```

---

## Position Sizing Rules of Thumb

| Rule | Value |
|------|-------|
| Max single trade | 5% of bankroll |
| Max correlated exposure | 15% of bankroll |
| Kelly multiplier | 0.25 (quarter) |
| Min edge to trade | 3% |
| Min liquidity | $500 |
| Max days to close | 90 |
