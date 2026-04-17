"""
pmbot entry point.

Usage:
    python -m src.main                  # single cycle
    python -m src.main --loop           # every 15 minutes
    python -m src.main --config path/to/other.yaml
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from src.logging_setup import setup_logging

app = typer.Typer(add_completion=False, help="Prediction market trading bot.")


@app.command()
def main(
    loop: Annotated[bool, typer.Option("--loop", help="Run on scheduled interval.")] = False,
    config: Annotated[str, typer.Option("--config", help="Override config file path.")] = "",
) -> None:
    # Late import so config override (if any) can be applied first
    if config:
        import src.config as _c
        _c.cfg = _c.load_config(default_path=Path(config))

    from src.config import cfg
    setup_logging(level=cfg.logging.level, log_file=cfg.logging.file, json=cfg.logging.json)

    from src.orchestrator.bot import Bot
    bot = Bot()

    if loop:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        import logging
        scheduler = AsyncIOScheduler()
        scheduler.add_job(bot.run_cycle, "interval", minutes=cfg.bot.cycle_interval_minutes)
        scheduler.start()
        logging.getLogger("apscheduler").setLevel(logging.WARNING)
        try:
            asyncio.get_event_loop().run_forever()
        except KeyboardInterrupt:
            pass
    else:
        asyncio.run(bot.run_cycle())


if __name__ == "__main__":
    app()
