"""
Kelly Criterion for binary prediction markets.

  b  = net odds = (1 - price) / price
  f* = (p·b - q) / b  =  (p - price) / (1 - price)

Apply fractional Kelly to account for model error (quarter-Kelly default).
"""
from __future__ import annotations


def kelly_fraction(our_prob: float, market_price: float, *, fractional: float = 0.25) -> float:
    if market_price <= 0 or market_price >= 1:
        return 0.0
    b = (1 - market_price) / market_price
    q = 1 - our_prob
    full_kelly = (our_prob * b - q) / b
    return max(0.0, min(full_kelly * fractional, 1.0))


def kelly_size(
    bankroll: float,
    our_prob: float,
    market_price: float,
    *,
    fractional: float = 0.25,
    max_fraction: float = 0.05,
) -> float:
    frac = kelly_fraction(our_prob, market_price, fractional=fractional)
    return round(bankroll * min(frac, max_fraction), 2)
