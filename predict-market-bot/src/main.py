"""
predict-market-bot — main entry point.

Runs one full scan → research → predict → risk → execute cycle.
In paper mode (default), no real orders are placed.

Usage:
    python -m src.main                  # single run
    python -m src.main --loop           # run every 15 minutes
    python -m src.main --mode paper     # force paper mode
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Annotated

import typer

from src.config import Settings, TradingMode, settings
from src.execution.paper import PaperExecutor
from src.execution.polymarket_executor import PolymarketExecutor
from src.execution.kalshi_executor import KalshiExecutor
from src.learning.tracker import PerformanceTracker, PredictionRecord
from src.models import Order, OrderSide
from src.prediction.baseline import BaselinePredictor
from src.research.researcher import MarketResearcher
from src.risk.manager import RiskManager
from src.scanners.polymarket import PolymarketScanner
from src.scanners.kalshi import KalshiScanner
from src.utils import get_logger, setup_logging

app = typer.Typer(add_completion=False)
logger = get_logger(__name__)

# Paper bankroll for simulation
_PAPER_BANKROLL = 10_000.0


async def run_cycle() -> None:
    """One full scan → predict → risk → execute cycle."""
    logger.info("cycle.start", mode=settings.trading_mode.value)

    # ── Executor ──────────────────────────────────────────────────────────────
    if settings.is_paper:
        executor = PaperExecutor()
    else:
        # TODO: Select executor based on platform of market
        raise RuntimeError("Live trading not yet enabled. Set TRADING_MODE=paper.")

    researcher = MarketResearcher()
    predictor = BaselinePredictor()
    tracker = PerformanceTracker()

    # ── Scan ──────────────────────────────────────────────────────────────────
    scanners = [PolymarketScanner(), KalshiScanner()]
    all_markets = []
    for scanner in scanners:
        markets = await scanner.scan()
        all_markets.extend(markets)

    logger.info("cycle.markets_found", count=len(all_markets))

    # ── Research → Predict → Risk → Execute ───────────────────────────────────
    open_positions: list = []   # TODO: load from position store
    risk = RiskManager(bankroll=_PAPER_BANKROLL, open_positions=open_positions)

    for market in all_markets:
        # Research
        research = await researcher.research(market)

        # Predict
        prediction = await predictor.predict(market, research)

        if not prediction.has_edge:
            logger.debug("cycle.no_edge", market_id=market.id)
            continue

        # Risk gate
        decision = risk.evaluate(prediction)
        if not decision.approved:
            logger.info("cycle.rejected", market_id=market.id, reason=decision.reason)
            continue

        # Size → Order
        market_price = (
            prediction.market_probability
            if prediction.edge > 0
            else 1 - prediction.market_probability
        )
        contracts = round(decision.size_usd / market_price, 2)
        order = Order(
            id=str(uuid.uuid4()),
            market_id=market.id,
            platform=market.platform.value,
            side=OrderSide.BUY,
            outcome=prediction.recommended_side,
            contracts=contracts,
            limit_price=market_price,
            paper=settings.is_paper,
        )

        # Execute
        trade = await executor.submit(order)
        logger.info(
            "cycle.executed",
            market_id=market.id,
            outcome=order.outcome,
            contracts=contracts,
            price=order.limit_price,
            paper=settings.is_paper,
        )

        # Track
        tracker.record(PredictionRecord(
            market_id=market.id,
            our_probability=prediction.our_probability,
            market_probability=prediction.market_probability,
            edge=prediction.edge,
            side=order.outcome,
            size_usd=decision.size_usd,
        ))

    logger.info("cycle.complete", summary=tracker.summary())


@app.command()
def main(
    loop: Annotated[bool, typer.Option("--loop", help="Run on a 15-minute schedule.")] = False,
    mode: Annotated[str, typer.Option("--mode", help="Override trading mode: paper|live.")] = "",
) -> None:
    setup_logging(level=settings.log_level, log_file=settings.log_file)

    if mode:
        # Allow CLI override without touching .env
        import os
        os.environ["TRADING_MODE"] = mode

    if loop:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(run_cycle, "interval", minutes=15)
        scheduler.start()
        try:
            asyncio.get_event_loop().run_forever()
        except KeyboardInterrupt:
            logger.info("bot.shutdown")
    else:
        asyncio.run(run_cycle())


if __name__ == "__main__":
    app()
