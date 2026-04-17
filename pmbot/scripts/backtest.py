"""
CLI: summarize paper trade JSONL logs.

Usage:
    python scripts/backtest.py
    python scripts/backtest.py --trades-dir data/trades
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from typing_extensions import Annotated

sys.path.insert(0, str(Path(__file__).parent.parent))

app = typer.Typer(add_completion=False)


@app.command()
def main(
    trades_dir: Annotated[str, typer.Option("--trades-dir")] = "data/trades",
) -> None:
    root = Path(trades_dir)
    if not root.exists():
        typer.echo(f"Directory not found: {root}", err=True)
        raise typer.Exit(1)

    records = []
    for f in sorted(root.glob("*.jsonl")):
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

    if not records:
        typer.echo("No trade records found.")
        return

    typer.echo(f"Total trades recorded:  {len(records)}")

    resolved = [r for r in records if r.get("resolved")]
    typer.echo(f"Resolved:               {len(resolved)}")

    if resolved:
        correct = sum(1 for r in resolved if r.get("outcome_correct"))
        accuracy = correct / len(resolved)
        total_pnl = sum(r.get("pnl") or 0.0 for r in resolved)
        avg_edge = sum(r.get("edge", 0.0) for r in resolved) / len(resolved)
        typer.echo(f"Accuracy:               {accuracy:.2%}")
        typer.echo(f"Total PnL (USD):        ${total_pnl:.2f}")
        typer.echo(f"Avg edge:               {avg_edge:+.4f}")
    else:
        typer.echo("No resolved trades yet — run the bot and resolve outcomes to see stats.")


if __name__ == "__main__":
    app()
