"""
CLI: compute Kelly stake size.

Usage:
    python scripts/kelly_size.py --our-prob 0.62 --market-prob 0.50 --bankroll 1000
"""
from __future__ import annotations

import typer
from typing_extensions import Annotated

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.risk.kelly import kelly_fraction, kelly_size

app = typer.Typer(add_completion=False)


@app.command()
def main(
    our_prob: Annotated[float, typer.Option("--our-prob", help="Our estimated probability (0–1).")],
    market_prob: Annotated[float, typer.Option("--market-prob", help="Current market price (0–1).")],
    bankroll: Annotated[float, typer.Option("--bankroll", help="Available bankroll in USD.")] = 1000.0,
    fraction: Annotated[float, typer.Option("--fraction", help="Fractional Kelly multiplier.")] = 0.25,
    max_pct: Annotated[float, typer.Option("--max-pct", help="Max % of bankroll per trade.")] = 0.05,
) -> None:
    frac = kelly_fraction(our_prob=our_prob, market_prob=market_prob, fraction=fraction)
    size = kelly_size(
        our_prob=our_prob,
        market_prob=market_prob,
        bankroll=bankroll,
        fraction=fraction,
        max_fraction=max_pct,
    )
    edge = our_prob - market_prob
    typer.echo(f"Edge:          {edge:+.4f}")
    typer.echo(f"Kelly f*:      {frac:.4f}")
    typer.echo(f"Stake (USD):   ${size:.2f}")
    if size == 0:
        typer.echo("No edge — no trade recommended.")


if __name__ == "__main__":
    app()
