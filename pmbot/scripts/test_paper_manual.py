"""
Manual paper trading engine walkthrough.

Shows the full lifecycle in one pass:
  1. Fill a YES order at limit
  2. Fill a NO order at limit
  3. Reject a too-tight limit
  4. Reject a duplicate market
  5. Mark-to-market (both sides, win + lose)
  6. Close a position -> realized PnL
  7. Show open_positions.json on disk
  8. Trip the STOP file -> submission halted
  9. Clear STOP -> submission resumes

Run:  python scripts/test_paper_manual.py

No assertions -- prints a readable narrative so you can eyeball the results.
All files live under a tmp dir so your real data/ is untouched.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.execution.orderbook import OrderBook
from src.execution.paper import PaperExecutor


_W = 72


def _banner(title: str) -> None:
    print(f"\n{'=' * _W}")
    print(f"  {title}")
    print(f"{'=' * _W}")


def _divider() -> None:
    print(f"  {'-' * (_W - 2)}")


def _book_for(bid: float, ask: float) -> OrderBook:
    """5-level synthetic book centred on bid/ask with deep size."""
    return OrderBook(
        bids=[(round(bid - 0.01 * i, 4), 500) for i in range(5)],
        asks=[(round(ask + 0.01 * i, 4), 500) for i in range(5)],
    )


def _show_positions(exec_: PaperExecutor) -> None:
    if not exec_.positions:
        print("  (no open positions)")
        return
    print(f"  {'market':<8} {'side':<4} {'entry':>6} {'mark':>6} "
          f"{'size':>8} {'contracts':>9} {'uPnL':>9}")
    for p in exec_.positions:
        print(f"  {p.market_id:<8} {p.side:<4} "
              f"{p.entry_price:>6.4f} {p.mark_price:>6.4f} "
              f"${p.size_usd:>7.2f} {p.contracts:>9.2f} "
              f"${p.unrealized_pnl:>+8.2f}")


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="paper_manual_"))
    print(f"Using tmp dir: {tmp}")

    ex = PaperExecutor(
        positions_file=tmp / "open_positions.json",
        trades_log=tmp / "trades.jsonl",
        closed_log=tmp / "closed_positions.jsonl",
        stop_file=tmp / "STOP",
    )

    # ── 1. YES fill at limit ────────────────────────────────────────────────
    _banner("1. YES fill at limit")
    book = _book_for(bid=0.60, ask=0.62)
    print(f"  Book:   best_bid=0.60  best_ask=0.62")
    print(f"  Order:  buy YES  $200 @ limit 0.62")
    rec = await ex.submit("m1", "poly", "yes", 200, 0.62, book)
    print(f"  Result: {'FILLED' if rec else 'REJECTED'}")
    if rec:
        print(f"          entry=${rec.fill_price:.4f}  "
              f"contracts={rec.contracts:.2f}  size=${rec.size_usd:.2f}")

    # ── 2. NO fill at limit ─────────────────────────────────────────────────
    _banner("2. NO fill at limit")
    print(f"  Book:   best_bid=0.60  best_ask=0.62")
    print(f"  Order:  buy NO   $200 @ limit 0.40 (needs YES bid >= 0.60)")
    rec = await ex.submit("m2", "poly", "no", 200, 0.40, book)
    print(f"  Result: {'FILLED' if rec else 'REJECTED'}")
    if rec:
        print(f"          NO entry=${rec.fill_price:.4f}  "
              f"contracts={rec.contracts:.2f}  size=${rec.size_usd:.2f}")

    # ── 3. Too-tight limit rejected ─────────────────────────────────────────
    _banner("3. Too-tight limit rejected")
    print(f"  Order:  buy YES  $200 @ limit 0.55 (best ask is 0.62)")
    rec = await ex.submit("m3", "poly", "yes", 200, 0.55, book)
    print(f"  Result: {'FILLED' if rec else 'REJECTED (limit unreachable)'}")

    # ── 4. Duplicate market rejected ────────────────────────────────────────
    _banner("4. Duplicate market rejected")
    print(f"  Already long m1 -- retry should bounce")
    rec = await ex.submit("m1", "poly", "yes", 100, 0.62, book)
    print(f"  Result: {'FILLED' if rec else 'REJECTED (already holding m1)'}")

    # ── 5. Mark-to-market ───────────────────────────────────────────────────
    _banner("5. Mark-to-market  (YES up, NO flat)")
    print(f"  m1 YES price moves 0.62 -> 0.72 (+10c)")
    print(f"  m2 YES price moves 0.60 -> 0.45 (NO 0.40 -> 0.55, +15c)")
    ex.mark_to_market({"m1": 0.72, "m2": 0.45})
    _divider()
    _show_positions(ex)

    # ── 6. Close m1 ─────────────────────────────────────────────────────────
    _banner("6. Close m1 at YES=0.80")
    pnl = ex.close_position("m1", yes_price=0.80)
    print(f"  Realised PnL: ${pnl:+.4f}")
    _divider()
    print("  Remaining open:")
    _show_positions(ex)

    # ── 7. open_positions.json on disk ──────────────────────────────────────
    _banner("7. data/trades/open_positions.json")
    data = json.loads((tmp / "open_positions.json").read_text())
    print(json.dumps(data, indent=2))

    # ── 8. STOP file halts submissions ──────────────────────────────────────
    _banner("8. Kill switch: create STOP file")
    (tmp / "STOP").write_text("halt")
    print(f"  is_halted() -> {ex.is_halted()}")
    rec = await ex.submit("m3", "poly", "yes", 200, 0.62, book)
    print(f"  Submit m3 -> {'FILLED' if rec else 'REJECTED (halted)'}")

    # ── 9. Remove STOP, resume ──────────────────────────────────────────────
    _banner("9. Remove STOP -- resume trading")
    (tmp / "STOP").unlink()
    print(f"  is_halted() -> {ex.is_halted()}")
    rec = await ex.submit("m3", "poly", "yes", 200, 0.62, book)
    print(f"  Submit m3 -> {'FILLED' if rec else 'REJECTED'}")

    # ── Summary ─────────────────────────────────────────────────────────────
    _banner("SUMMARY")
    for k, v in ex.summary().items():
        print(f"  {k:<22} {v}")
    _divider()
    _show_positions(ex)
    print()


if __name__ == "__main__":
    asyncio.run(main())
