"""
pmbot entry point.

Usage:
    python -m src.main run-once                  # single cycle, then exit
    python -m src.main loop                      # every cycle_interval_minutes
    python -m src.main run-once --config path    # override config file
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from src.logging_setup import get_logger, setup_logging

app = typer.Typer(add_completion=False, help="Prediction market trading bot.")
logger = get_logger(__name__)


def _bootstrap(config: str) -> None:
    """Apply config override (if any) and initialise logging once."""
    if config:
        import src.config as _c
        _c.cfg = _c.load_config(default_path=Path(config))

    from src.config import cfg
    setup_logging(level=cfg.logging.level, log_file=cfg.logging.file, json=cfg.logging.json)


@app.command("run-once")
def run_once(
    config: Annotated[str, typer.Option("--config", help="Override config file path.")] = "",
) -> None:
    """Run a single pipeline cycle and exit."""
    _bootstrap(config)
    from src.orchestrator.bot import Bot

    bot = Bot()
    try:
        report = asyncio.run(bot.run_cycle())
    except Exception as exc:
        logger.exception("run_once.crashed", error=str(exc))
        raise typer.Exit(code=1)

    typer.echo(f"cycle complete: {report.as_dict()}")


@app.command("loop")
def loop(
    config: Annotated[str, typer.Option("--config", help="Override config file path.")] = "",
) -> None:
    """Run cycles on a schedule until interrupted."""
    _bootstrap(config)

    from src.config import cfg
    from src.orchestrator.bot import Bot

    bot = Bot()

    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    import logging

    scheduler = AsyncIOScheduler()
    scheduler.add_job(bot.run_cycle, "interval", minutes=cfg.bot.cycle_interval_minutes)
    scheduler.start()
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logger.info("loop.started", interval_min=cfg.bot.cycle_interval_minutes)
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        logger.info("loop.stopped")


if __name__ == "__main__":
    app()
