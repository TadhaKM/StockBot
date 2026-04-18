"""
Manual risk validation test cases.

Six scenarios from the checklist plus a bankroll-scaling sanity check.
Run:  python scripts/test_risk_manual.py

No assertions -- prints a readable table so you can eyeball the results.
Every case shows the expected verdict, the actual verdict, and every
failure reason.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.validate_risk import validate_risk


_W = 72


# ── Scenario definition ──────────────────────────────────────────────────────

@dataclass
class Scenario:
    name: str
    description: str
    expected: str          # human description: "ALLOWED", "BLOCKED on <reason>", etc.
    expected_allowed: bool
    params: dict


SCENARIOS: list[Scenario] = [
    Scenario(
        name="1. CLEAN PASS",
        description="Good edge, decent bankroll, low exposure, no drawdown",
        expected="ALLOWED with positive size",
        expected_allowed=True,
        params=dict(
            p_model=0.65, p_market=0.50, confidence=0.72,
            bankroll=10_000.0,
            total_exposure_fraction=0.10,
            daily_loss_fraction=0.02,
            drawdown_fraction=0.03,
        ),
    ),
    Scenario(
        name="2. OVERSIZED POSITION",
        description="Tiny bankroll + huge edge -- Kelly wants lots, cap saves us",
        expected="ALLOWED but size capped at 5% of bankroll",
        expected_allowed=True,
        params=dict(
            p_model=0.90, p_market=0.50, confidence=0.80,
            bankroll=500.0,  # tiny bankroll
            total_exposure_fraction=0.0,
            daily_loss_fraction=0.0,
            drawdown_fraction=0.0,
        ),
    ),
    Scenario(
        name="3. EXPOSURE BREACH",
        description="Existing exposure already at 25% (limit is 20%)",
        expected="BLOCKED on exposure",
        expected_allowed=False,
        params=dict(
            p_model=0.65, p_market=0.50, confidence=0.72,
            bankroll=10_000.0,
            total_exposure_fraction=0.25,
            daily_loss_fraction=0.02,
            drawdown_fraction=0.03,
        ),
    ),
    Scenario(
        name="4. DRAWDOWN STOP",
        description="Drawdown at 10% from peak (limit is 8%)",
        expected="BLOCKED on drawdown",
        expected_allowed=False,
        params=dict(
            p_model=0.65, p_market=0.50, confidence=0.72,
            bankroll=10_000.0,
            total_exposure_fraction=0.10,
            daily_loss_fraction=0.02,
            drawdown_fraction=0.10,
        ),
    ),
    Scenario(
        name="5. DAILY LOSS STOP",
        description="Daily PnL already at -12% (limit is 10%)",
        expected="BLOCKED on daily loss",
        expected_allowed=False,
        params=dict(
            p_model=0.65, p_market=0.50, confidence=0.72,
            bankroll=10_000.0,
            total_exposure_fraction=0.10,
            daily_loss_fraction=0.12,
            drawdown_fraction=0.03,
        ),
    ),
    Scenario(
        name="6. WEAK EDGE",
        description="p_model - p_market = 0.02 (below min_edge of 0.05)",
        expected="BLOCKED on edge",
        expected_allowed=False,
        params=dict(
            p_model=0.52, p_market=0.50, confidence=0.72,
            bankroll=10_000.0,
            total_exposure_fraction=0.10,
            daily_loss_fraction=0.02,
            drawdown_fraction=0.03,
        ),
    ),
]


# ── Runner ───────────────────────────────────────────────────────────────────

def run_scenario(s: Scenario) -> bool:
    print(f"\n{'=' * _W}")
    print(f"  {s.name}")
    print(f"{'=' * _W}")
    print(f"  What:     {s.description}")
    print(f"  Expected: {s.expected}")

    p = s.params
    print(
        f"  Inputs:   p_model={p['p_model']:.2f} p_market={p['p_market']:.2f} "
        f"conf={p['confidence']:.2f} bankroll=${p['bankroll']:,.0f}"
    )
    print(
        f"            exposure={p['total_exposure_fraction']:.0%} "
        f"daily_loss={p['daily_loss_fraction']:.0%} drawdown={p['drawdown_fraction']:.0%}"
    )
    print(f"  {'-' * (_W - 2)}")

    v = validate_risk(**p)

    verdict_line = (
        f"ALLOWED  ${v.position_size_usd:,.2f}" if v.allowed
        else f"BLOCKED  $0.00"
    )
    print(f"  Got:      {verdict_line}")

    if v.reasons:
        print(f"  Reasons:")
        for r in v.reasons:
            print(f"    - {r}")

    # Compare against expected
    passed = v.allowed == s.expected_allowed
    mark = "PASS" if passed else "FAIL"
    print(f"  Verdict:  {mark}")
    return passed


def run_bankroll_scaling() -> bool:
    """Bonus: sizing should scale linearly with bankroll."""
    print(f"\n{'=' * _W}")
    print(f"  BONUS: BANKROLL SCALING")
    print(f"{'=' * _W}")
    print(f"  What:     Same trade at three bankroll levels")
    print(f"  Expected: position size scales linearly (smaller bankroll = smaller size)")
    print(f"  {'-' * (_W - 2)}")

    base = dict(
        p_model=0.65, p_market=0.50, confidence=0.72,
        total_exposure_fraction=0.10,
        daily_loss_fraction=0.02,
        drawdown_fraction=0.03,
    )

    sizes = []
    for bankroll in [1_000.0, 5_000.0, 10_000.0]:
        v = validate_risk(**base, bankroll=bankroll)
        print(f"  bankroll=${bankroll:>8,.0f}  ->  size=${v.position_size_usd:>7,.2f}  "
              f"({v.position_size_usd / bankroll:.2%} of bankroll)")
        sizes.append((bankroll, v.position_size_usd))

    # Check linearity: size/bankroll should be roughly constant
    ratios = [s / b for b, s in sizes]
    spread = max(ratios) - min(ratios)
    passed = spread < 0.001  # all ratios essentially equal
    mark = "PASS" if passed else "FAIL"
    print(f"  Verdict:  {mark}  (size/bankroll spread = {spread:.4%})")
    return passed


if __name__ == "__main__":
    results: list[tuple[str, bool]] = []

    for scenario in SCENARIOS:
        results.append((scenario.name, run_scenario(scenario)))

    results.append(("BONUS: Bankroll scaling", run_bankroll_scaling()))

    # Summary
    print(f"\n{'=' * _W}")
    print(f"  SUMMARY")
    print(f"{'=' * _W}")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        mark = "PASS" if ok else "FAIL"
        print(f"  {mark}  {name}")
    print(f"\n  {passed}/{total} scenarios passed")
    print(f"{'=' * _W}\n")

    sys.exit(0 if passed == total else 1)
