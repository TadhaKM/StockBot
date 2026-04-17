"""
CLI tool: compute Kelly sizing for a given edge.

Usage:
    python scripts/kelly_size.py --prob 0.65 --price 0.55 --bankroll 10000
"""
from __future__ import annotations

import typer

app = typer.Typer()


@app.command()
def main(
    prob: float = typer.Option(..., help="Our estimated probability (0–1)."),
    price: float = typer.Option(..., help="Market price for the outcome (0–1)."),
    bankroll: float = typer.Option(10_000, help="Total bankroll in USD."),
    fractional: float = typer.Option(0.25, help="Fractional Kelly multiplier."),
    max_frac: float = typer.Option(0.05, help="Hard cap as fraction of bankroll."),
) -> None:
    import sys
    sys.path.insert(0, ".")
    from src.risk.kelly import kelly_fraction, kelly_size

    frac = kelly_fraction(prob, price, fractional=fractional)
    size = kelly_size(bankroll, prob, price, fractional=fractional, max_fraction=max_frac)
    edge = prob - price

    typer.echo(f"\n{'─'*40}")
    typer.echo(f"  Our probability :  {prob:.1%}")
    typer.echo(f"  Market price    :  {price:.1%}")
    typer.echo(f"  Edge            :  {edge:+.1%}")
    typer.echo(f"  Kelly fraction  :  {frac:.4f}  ({frac:.2%} of bankroll)")
    typer.echo(f"  Wager (capped)  :  ${size:,.2f}")
    typer.echo(f"{'─'*40}\n")

    if edge <= 0:
        typer.secho("  No edge — do not bet.", fg=typer.colors.RED)


if __name__ == "__main__":
    app()
