"""
pmbot entry point.

Usage:
    python -m src.main run-once         # single cycle (paper trades)
    python -m src.main loop             # scheduled cycles (paper trades)
    python -m src.main observe-once     # single cycle, NO trades -- logs candidates
    python -m src.main observe-loop     # scheduled, NO trades -- logs candidates

Observe mode writes would-be trades to data/logs/candidate_trades.jsonl
with timestamp, prices, edge, confidence, and any reject reasons.
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


def _run_single(observe: bool) -> None:
    from src.orchestrator.bot import Bot

    bot = Bot(observe=observe)
    try:
        report = asyncio.run(bot.run_cycle())
    except Exception as exc:
        logger.exception("cycle.crashed", observe=observe, error=str(exc))
        raise typer.Exit(code=1)

    label = "observe" if observe else "cycle"
    typer.echo(f"{label} complete: {report.as_dict()}")


def _run_loop(observe: bool) -> None:
    from src.config import cfg
    from src.orchestrator.bot import Bot
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    import logging

    bot = Bot(observe=observe)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(bot.run_cycle, "interval", minutes=cfg.bot.cycle_interval_minutes)
    scheduler.start()
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logger.info(
        "loop.started",
        interval_min=cfg.bot.cycle_interval_minutes,
        observe=observe,
    )
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        logger.info("loop.stopped")


# ── Trading commands ────────────────────────────────────────────────────────

@app.command("run-once")
def run_once(
    config: Annotated[str, typer.Option("--config", help="Override config file path.")] = "",
) -> None:
    """Run a single pipeline cycle and exit (paper trades enabled)."""
    _bootstrap(config)
    _run_single(observe=False)


@app.command("loop")
def loop(
    config: Annotated[str, typer.Option("--config", help="Override config file path.")] = "",
) -> None:
    """Run cycles on a schedule until interrupted (paper trades enabled)."""
    _bootstrap(config)
    _run_loop(observe=False)


# ── Observation commands ────────────────────────────────────────────────────

@app.command("observe-once")
def observe_once(
    config: Annotated[str, typer.Option("--config", help="Override config file path.")] = "",
) -> None:
    """Run one cycle WITHOUT executing -- log candidate trades to JSONL."""
    _bootstrap(config)
    _run_single(observe=True)


@app.command("observe-loop")
def observe_loop(
    config: Annotated[str, typer.Option("--config", help="Override config file path.")] = "",
) -> None:
    """Run cycles on a schedule WITHOUT executing -- log candidates to JSONL."""
    _bootstrap(config)
    _run_loop(observe=True)


if __name__ == "__main__":
    app()
