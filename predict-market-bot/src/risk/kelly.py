"""
Kelly Criterion sizing for binary prediction markets.

For a binary market where:
  p  = our estimated probability of YES
  q  = 1 - p
  b  = net odds on a $1 YES bet = (1 - price) / price  (i.e. payout per $ risked)

Full Kelly fraction of bankroll = (p * b - q) / b = (p - price) / (1 - price)

We always apply a fractional multiplier (quarter-Kelly by default) to account
for estimation error and correlation risk.
"""
from __future__ import annotations


def kelly_fraction(
    our_prob: float,
    market_price: float,
    *,
    fractional: float = 0.25,
) -> float:
    """
    Return the Kelly-optimal fraction of bankroll to wager.

    Args:
        our_prob: Our estimated probability (0–1).
        market_price: Current market price for the outcome (0–1).
        fractional: Multiplier < 1.0 to reduce full Kelly (quarter-Kelly = 0.25).

    Returns:
        Fraction in [0, 1]. Returns 0 if bet has no edge.
    """
    if market_price <= 0 or market_price >= 1:
        return 0.0

    b = (1 - market_price) / market_price   # net odds
    q = 1 - our_prob
    full_kelly = (our_prob * b - q) / b

    # Only bet if positive edge
    if full_kelly <= 0:
        return 0.0

    return min(full_kelly * fractional, 1.0)


def kelly_size(
    bankroll: float,
    our_prob: float,
    market_price: float,
    *,
    fractional: float = 0.25,
    max_fraction: float = 0.05,
) -> float:
    """
    Return the dollar amount to wager given a bankroll.

    Args:
        bankroll: Total available capital in USD.
        our_prob: Our estimated probability.
        market_price: Current market price.
        fractional: Fractional Kelly multiplier.
        max_fraction: Hard cap — never bet more than this fraction of bankroll.

    Returns:
        Dollar amount to wager (may be 0 if no edge).
    """
    frac = kelly_fraction(our_prob, market_price, fractional=fractional)
    capped = min(frac, max_fraction)
    return round(bankroll * capped, 2)
