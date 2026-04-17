"""
Simple backtest runner over historical paper trade logs.

Reads data/paper_trades/*.jsonl and computes P&L, accuracy, and
edge-bucket calibration.

TODO: Add proper historical market data source.
TODO: Support walk-forward validation windows.
TODO: Compare multiple predictor versions.

Usage:
    python scripts/backtest.py --dir data/paper_trades
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

app = typer.Typer()


@app.command()
def main(
    directory: Path = typer.Option(Path("data/paper_trades"), "--dir", help="Trade log directory."),
) -> None:
    sys.path.insert(0, ".")

    records = []
    for f in sorted(directory.glob("*.jsonl")):
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

    if not records:
        typer.echo("No trade records found.")
        raise typer.Exit()

    typer.echo(f"\nBacktest over {len(records)} trades\n{'─'*40}")

    # TODO: For each resolved trade, compute actual P&L.
    # Currently paper trades don't carry resolution data — this is a placeholder.
    typer.echo(f"  Total trades recorded : {len(records)}")
    typer.echo(f"  (Resolution data not yet populated — wire up tracker.resolve())")
    typer.echo(f"{'─'*40}\n")


if __name__ == "__main__":
    app()
