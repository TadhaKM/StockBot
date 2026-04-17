"""
Nightly review script.

Intended to run via cron at ~midnight:
  0 0 * * * cd /path/to/bot && python scripts/nightly_review.py >> data/logs/nightly.log 2>&1

Produces a Markdown summary of the day's activity and appends it to
references/failure_log.md if any trades moved against our prediction.

TODO: Add email/Slack notification.
TODO: Check for markets resolving tomorrow and flag for manual review.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, ".")

from src.config import settings
from src.utils import get_logger, setup_logging

setup_logging(level=settings.log_level)
logger = get_logger(__name__)


def main() -> None:
    today = date.today().isoformat()
    trade_log = Path(f"data/paper_trades/{today}.jsonl")

    if not trade_log.exists():
        logger.info("nightly.no_trades", date=today)
        return

    trades = []
    with trade_log.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                trades.append(json.loads(line))

    logger.info("nightly.summary", date=today, trade_count=len(trades))

    # TODO: Fetch current prices for each open position and mark-to-market.
    # TODO: Identify trades where our prediction is currently losing.
    # TODO: Append to references/failure_log.md with structured notes.

    print(f"\n=== Nightly Review: {today} ===")
    print(f"Trades today : {len(trades)}")
    print("(Full P&L unavailable until market resolution is wired in.)\n")


if __name__ == "__main__":
    main()
