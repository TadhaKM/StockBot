"""
Deterministic risk validation.

Runs every risk gate in sequence and returns: allowed, position_size, reasons.
All gates are evaluated (no early exit) so you see every failure at once.

Gates (in order):
  1. Edge         |p_model - p_market| >= min_edge
  2. Confidence   confidence >= min_confidence
  3. Portfolio    total_exposure / daily_loss / drawdown within YAML limits
  4. Sizing       fractional Kelly, hard-capped at max_position_size

Usage:
    python scripts/validate_risk.py \\
        --p-model 0.65 --p-market 0.50 --confidence 0.72 \\
        --bankroll 10000 \\
        --exposure 0.12 --daily-loss 0.02 --drawdown 0.03

Failing example (breaches all limits):
    python scripts/validate_risk.py \\
        --p-model 0.52 --p-market 0.50 --confidence 0.40 \\
        --bankroll 10000 \\
        --exposure 0.25 --daily-loss 0.12 --drawdown 0.10
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import typer
from typing_extensions import Annotated

from src.config.rules import BotState, load_rules
from src.risk.kelly import kelly_fraction, kelly_size

app = typer.Typer(add_completion=False)

_W = 52  # total line width


# ── Core validation (importable by tests) ────────────────────────────────────

@dataclass
class RiskVerdict:
    allowed: bool
    position_size_usd: float
    reasons: list[str] = field(default_factory=list)
    # Gate details: (label, passed, detail_string)
    gates: list[tuple[str, bool, str]] = field(default_factory=list)


def validate_risk(
    *,
    p_model: float,
    p_market: float,
    confidence: float,
    bankroll: float,
    total_exposure_fraction: float = 0.0,
    daily_loss_fraction: float = 0.0,
    drawdown_fraction: float = 0.0,
) -> RiskVerdict:
    """
    Run all risk gates deterministically. Never short-circuits.

    Returns a RiskVerdict with:
      .allowed           -- True only when every gate passes
      .position_size_usd -- Kelly-sized stake (0 if any gate failed)
      .reasons           -- every failure message collected
      .gates             -- per-gate (label, passed, detail) for display
    """
    rules = load_rules()
    er = rules.edge
    sr = rules.sizing

    failures: list[str] = []
    gates: list[tuple[str, bool, str]] = []

    edge = p_model - p_market

    # ── Gate 1: Edge ─────────────────────────────────────────────────────────
    edge_ok = abs(edge) >= er.min_edge
    if not edge_ok:
        failures.append(f"edge {abs(edge):.4f} < min {er.min_edge:.4f}")
    gates.append((
        "Edge",
        edge_ok,
        f"|{edge:+.4f}| vs min {er.min_edge:.4f}",
    ))

    # ── Gate 2: Confidence ───────────────────────────────────────────────────
    conf_ok = confidence >= er.min_confidence
    if not conf_ok:
        failures.append(f"confidence {confidence:.4f} < min {er.min_confidence:.4f}")
    gates.append((
        "Confidence",
        conf_ok,
        f"{confidence:.4f} vs min {er.min_confidence:.4f}",
    ))

    # ── Gate 3: Portfolio (all three sub-checks, no short-circuit) ───────────
    state = BotState(
        total_exposure_fraction=total_exposure_fraction,
        daily_loss_fraction=daily_loss_fraction,
        drawdown_fraction=drawdown_fraction,
    )

    exp_ok = state.total_exposure_fraction < sr.max_total_exposure
    if not exp_ok:
        failures.append(
            f"exposure {state.total_exposure_fraction:.2%} >= limit {sr.max_total_exposure:.2%}"
        )
    gates.append((
        "Exposure",
        exp_ok,
        f"{state.total_exposure_fraction:.2%} < limit {sr.max_total_exposure:.2%}",
    ))

    loss_ok = state.daily_loss_fraction < sr.max_daily_loss
    if not loss_ok:
        failures.append(
            f"daily_loss {state.daily_loss_fraction:.2%} >= limit {sr.max_daily_loss:.2%}"
        )
    gates.append((
        "Daily loss",
        loss_ok,
        f"{state.daily_loss_fraction:.2%} < limit {sr.max_daily_loss:.2%}",
    ))

    dd_ok = state.drawdown_fraction < sr.max_drawdown
    if not dd_ok:
        failures.append(
            f"drawdown {state.drawdown_fraction:.2%} >= limit {sr.max_drawdown:.2%}"
        )
    gates.append((
        "Drawdown",
        dd_ok,
        f"{state.drawdown_fraction:.2%} < limit {sr.max_drawdown:.2%}",
    ))

    # ── Gate 4: Kelly sizing ─────────────────────────────────────────────────
    # Use correct side: positive edge = buy YES at p_market, else buy NO at 1-p_market
    if edge >= 0:
        prob, price = p_model, p_market
    else:
        prob, price = 1 - p_model, 1 - p_market

    full_frac = kelly_fraction(prob, price, fractional=1.0)
    frac_kelly = full_frac * sr.kelly_fraction
    capped = min(frac_kelly, sr.max_position_size)
    size = kelly_size(bankroll, prob, price, fractional=sr.kelly_fraction, max_fraction=sr.max_position_size)

    kelly_ok = size > 0.0
    if not kelly_ok:
        failures.append("Kelly sizing returned 0 -- no positive edge after costs")
    was_capped = capped < frac_kelly - 1e-9
    cap_note = f" [capped at {sr.max_position_size:.0%}]" if was_capped else ""
    gates.append((
        "Kelly sizing",
        kelly_ok,
        f"full={full_frac:.4f}  x{sr.kelly_fraction}={frac_kelly:.4f}  capped={capped:.4f}{cap_note}",
    ))

    allowed = len(failures) == 0
    return RiskVerdict(
        allowed=allowed,
        position_size_usd=size if allowed else 0.0,
        reasons=failures,
        gates=gates,
    )


# ── CLI display ──────────────────────────────────────────────────────────────

def _gate_line(label: str, passed: bool, detail: str) -> str:
    status = "PASS" if passed else "FAIL"
    return f"  {status}  {label:<14} {detail}"


@app.command()
def main(
    p_model: Annotated[float, typer.Option("--p-model", help="Model probability (0-1).")],
    p_market: Annotated[float, typer.Option("--p-market", help="Market implied probability (0-1).")],
    confidence: Annotated[float, typer.Option("--confidence", help="Model confidence (0-1).")] = 0.70,
    bankroll: Annotated[float, typer.Option("--bankroll", help="Available bankroll in USD.")] = 10_000.0,
    exposure: Annotated[float, typer.Option("--exposure", help="Current exposure as fraction of bankroll.")] = 0.0,
    daily_loss: Annotated[float, typer.Option("--daily-loss", help="Today's realised loss as fraction of bankroll.")] = 0.0,
    drawdown: Annotated[float, typer.Option("--drawdown", help="Drawdown from peak equity as fraction.")] = 0.0,
) -> None:
    verdict = validate_risk(
        p_model=p_model,
        p_market=p_market,
        confidence=confidence,
        bankroll=bankroll,
        total_exposure_fraction=exposure,
        daily_loss_fraction=daily_loss,
        drawdown_fraction=drawdown,
    )

    edge = p_model - p_market
    side = "YES" if edge >= 0 else "NO"

    typer.echo("=" * _W)
    typer.echo("  Risk Validation")
    typer.echo("=" * _W)
    typer.echo(f"  p_model     {p_model:.4f}   p_market  {p_market:.4f}")
    typer.echo(f"  edge       {edge:+.4f}   side      {side}")
    typer.echo(f"  confidence  {confidence:.4f}   bankroll  ${bankroll:,.2f}")
    typer.echo("-" * _W)

    for label, passed, detail in verdict.gates:
        typer.echo(_gate_line(label, passed, detail))

    typer.echo("=" * _W)

    if verdict.allowed:
        typer.echo(f"  ALLOWED   ${verdict.position_size_usd:,.2f}")
    else:
        typer.echo(f"  BLOCKED   $0.00")
        for r in verdict.reasons:
            typer.echo(f"    - {r}")

    typer.echo("=" * _W)

    raise typer.Exit(0 if verdict.allowed else 1)


if __name__ == "__main__":
    app()
