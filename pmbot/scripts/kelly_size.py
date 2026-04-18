"""
CLI: compute fractional Kelly stake size for a binary prediction market.

Usage:
    python scripts/kelly_size.py --p-model 0.65 --p-market 0.50 --bankroll 1000

Options:
    --p-model    Model's estimated probability that YES resolves (0-1)
    --p-market   Current market price / implied probability (0-1)
    --bankroll   Available bankroll in USD          [default: 1000]
    --fraction   Fractional Kelly multiplier        [default: 0.25]
    --max-pct    Hard cap: max % of bankroll / trade [default: 0.05]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import typer
from typing_extensions import Annotated

from src.risk.kelly import kelly_fraction, kelly_size

app = typer.Typer(add_completion=False)

_SEP = "-" * 40


@app.command()
def main(
    p_model: Annotated[float, typer.Option("--p-model", help="Model probability (0-1).")],
    p_market: Annotated[float, typer.Option("--p-market", help="Market price / implied prob (0-1).")],
    bankroll: Annotated[float, typer.Option("--bankroll", help="Bankroll in USD.")] = 1000.0,
    fraction: Annotated[float, typer.Option("--fraction", help="Fractional Kelly multiplier.")] = 0.25,
    max_pct: Annotated[float, typer.Option("--max-pct", help="Max fraction of bankroll per trade.")] = 0.05,
) -> None:

    edge = p_model - p_market
    if abs(edge) < 1e-9:
        typer.echo("Edge = 0.0000 -- no trade recommended.")
        raise typer.Exit(0)

    # When edge is negative the trade is on the NO side:
    # use (1-p_market) as the price and (1-p_model) as our probability.
    if edge > 0:
        side = "YES"
        prob, price = p_model, p_market
    else:
        side = "NO"
        prob, price = 1 - p_model, 1 - p_market

    frac = kelly_fraction(prob, price, fractional=fraction)
    raw_size = bankroll * frac
    size = kelly_size(bankroll, prob, price, fractional=fraction, max_fraction=max_pct)
    capped = size < raw_size - 0.01

    typer.echo(_SEP)
    typer.echo(f"  p_model     {p_model:.4f}")
    typer.echo(f"  p_market    {p_market:.4f}")
    typer.echo(f"  edge       {edge:+.4f}   -> trade {side}")
    typer.echo(f"  bankroll   ${bankroll:,.2f}")
    typer.echo(_SEP)
    typer.echo(f"  full Kelly  {frac / fraction:.4f}  ({frac / fraction * 100:.2f}% of bankroll)")
    typer.echo(f"  x{fraction} frac    {frac:.4f}  ({frac * 100:.2f}% of bankroll)")
    if capped:
        typer.echo(f"  capped at   {max_pct:.4f}  ({max_pct * 100:.2f}% of bankroll -- hard limit)")
    typer.echo(_SEP)
    typer.echo(f"  STAKE       ${size:,.2f}")
    if size == 0.0:
        typer.echo("  No edge after Kelly -- no trade recommended.")


if __name__ == "__main__":
    app()
