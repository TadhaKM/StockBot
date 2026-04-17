"""
CLI: validate config and print effective settings.

Usage:
    python scripts/validate_config.py
    python scripts/validate_config.py --config config/default.yaml
"""
from __future__ import annotations

import sys
from pathlib import Path

import typer
from typing_extensions import Annotated

sys.path.insert(0, str(Path(__file__).parent.parent))

app = typer.Typer(add_completion=False)


@app.command()
def main(
    config: Annotated[str, typer.Option("--config", help="Path to config YAML.")] = "",
) -> None:
    from src.config import load_config

    path = Path(config) if config else Path("config/default.yaml")
    try:
        cfg = load_config(default_path=path)
    except Exception as exc:
        typer.echo(f"[ERROR] Config failed to load: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo("Config loaded successfully.\n")
    typer.echo(f"  trading_mode:            {cfg.bot.trading_mode}")
    typer.echo(f"  cycle_interval_minutes:  {cfg.bot.cycle_interval_minutes}")
    typer.echo(f"  bankroll_usd:            {cfg.risk.bankroll_usd}")
    typer.echo(f"  max_bankroll_fraction:   {cfg.risk.max_bankroll_fraction}")
    typer.echo(f"  max_open_positions:      {cfg.risk.max_open_positions}")
    typer.echo(f"  min_edge_threshold:      {cfg.risk.min_edge_threshold}")
    typer.echo(f"  kelly_fraction:          {cfg.risk.kelly_fraction}")
    typer.echo(f"  polymarket enabled:      {cfg.platforms.polymarket is not None}")
    typer.echo(f"  kalshi enabled:          {cfg.platforms.kalshi is not None}")
    typer.echo(f"  logging level:           {cfg.logging.level}")
    typer.echo("\nAll checks passed.")


if __name__ == "__main__":
    app()
