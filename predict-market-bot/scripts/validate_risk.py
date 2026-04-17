"""
Validate risk settings from .env / config against sanity thresholds.
Run before going live to catch misconfigured limits.

Usage:
    python scripts/validate_risk.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from src.config import settings


def check(condition: bool, msg: str, fatal: bool = False) -> bool:
    if condition:
        print(f"  ✓  {msg}")
        return True
    else:
        prefix = "✗ FATAL" if fatal else "⚠ WARN "
        print(f"  {prefix}  {msg}")
        return not fatal


def main() -> None:
    print("\nRisk configuration validation\n" + "─" * 40)
    ok = True

    ok &= check(settings.is_paper or settings.polymarket_api_key != "", "API key set (or paper mode)")
    ok &= check(settings.max_bankroll_fraction <= 0.10, f"Max bankroll fraction {settings.max_bankroll_fraction:.0%} ≤ 10%", fatal=True)
    ok &= check(settings.kelly_fraction <= 0.50, f"Kelly fraction {settings.kelly_fraction:.0%} ≤ 50%", fatal=True)
    ok &= check(settings.min_edge_threshold >= 0.02, f"Min edge {settings.min_edge_threshold:.0%} ≥ 2%")
    ok &= check(settings.max_open_positions <= 20, f"Max open positions {settings.max_open_positions} ≤ 20")
    ok &= check(settings.is_paper, "Paper mode active (safe default)")

    print("─" * 40)
    if ok:
        print("All checks passed.\n")
    else:
        print("One or more fatal checks failed. Fix before going live.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
