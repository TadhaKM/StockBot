"""
Manual order book test cases.

Three books -- good, bad, trap -- each tested at three order sizes.
Run:  python scripts/test_orderbook_manual.py

No assertions -- prints a readable table so you can eyeball the results.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging, warnings
warnings.filterwarnings("ignore")

from src.config.rules import load_rules
from src.execution.orderbook import OrderBook

# Suppress all logging: stdlib handlers + structlog reconfigure
logging.root.setLevel(logging.CRITICAL + 1)
for h in logging.root.handlers[:]:
    logging.root.removeHandler(h)
logging.root.addHandler(logging.NullHandler())

import structlog
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL),
    logger_factory=structlog.PrintLoggerFactory(file=open("NUL", "w")),
    cache_logger_on_first_use=False,
)

rules = load_rules()

SIZES = [25, 200, 800]  # tiny, medium, larger

# -----------------------------------------------------------------------------
# 1. GOOD BOOK
#    Tight spread, heavy depth near mid, low slippage for moderate sizes.
#    Expect: safe at all three sizes.
# -----------------------------------------------------------------------------
good_book = OrderBook(
    bids=[
        (0.61, 2000),
        (0.60, 1500),
        (0.59, 1000),
        (0.58, 800),
        (0.57, 500),
    ],
    asks=[
        (0.62, 2000),
        (0.63, 1500),
        (0.64, 1000),
        (0.65, 800),
        (0.66, 500),
    ],
)

# -----------------------------------------------------------------------------
# 2. BAD BOOK
#    Wide spread, almost no depth on either side.
#    Expect: unsafe at every size.
# -----------------------------------------------------------------------------
bad_book = OrderBook(
    bids=[
        (0.40, 15),
        (0.35, 10),
    ],
    asks=[
        (0.55, 15),
        (0.60, 10),
    ],
)

# -----------------------------------------------------------------------------
# 3. TRAP BOOK
#    Headline quote looks great: 0.60/0.62, tight 2-cent spread.
#    But only $5 rests at each top level -- real size slams into bad fills.
#    Expect: tiny order = safe, medium+ = slippage blows up.
# -----------------------------------------------------------------------------
trap_book = OrderBook(
    bids=[
        (0.60, 5),     # bait -- almost nothing here
        (0.52, 50),
        (0.45, 200),
        (0.40, 500),
    ],
    asks=[
        (0.62, 5),     # bait -- almost nothing here
        (0.70, 50),
        (0.78, 200),
        (0.85, 500),
    ],
)


# -----------------------------------------------------------------------------
# Runner
# -----------------------------------------------------------------------------
def run_scenario(name: str, book: OrderBook) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {name}")
    print(f"{'=' * 72}")
    print(f"  best_bid={book.best_bid}  best_ask={book.best_ask}  "
          f"spread={book.spread:.4f}  mid={book.mid_price:.4f}")
    print(f"  total_bid_depth=${book.total_bid_depth:.0f}  "
          f"total_ask_depth=${book.total_ask_depth:.0f}  "
          f"depth_near_mid=${book.depth_within(rules.execution.depth_band):.0f}")
    print()

    header = f"  {'Side':<5} {'Size':>7} | {'Fill':>7} {'Slip':>8} {'Lvls':>5} {'Filled?':>8} | {'Safe?':>6}  Reason"
    print(header)
    print(f"  {'-' * len(header)}")

    for side in ("yes", "no"):
        for size in SIZES:
            fill = book.estimate_fill_price(side, size)
            safe = book.is_trade_safe(side, size, rules)

            reason = ", ".join(safe.failures) if safe.failures else "--"
            print(
                f"  {side:<5} ${size:>6} | "
                f"{fill.fill_price:>7.4f} {fill.slippage:>7.4f}  {fill.levels_consumed:>4}  "
                f"{'yes' if fill.fully_filled else 'NO':>7} | "
                f"{'PASS' if safe.passed else 'FAIL':>5}   {reason}"
            )
        print()


if __name__ == "__main__":
    run_scenario("GOOD BOOK -- tight spread, deep liquidity", good_book)
    run_scenario("BAD BOOK -- wide spread, almost no depth", bad_book)
    run_scenario("TRAP BOOK -- nice headline, nothing behind it", trap_book)
