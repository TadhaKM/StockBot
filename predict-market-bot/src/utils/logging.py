"""Structured logging setup using structlog + rich."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog
from rich.logging import RichHandler


def setup_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    """Call once at startup to configure structlog."""
    log_file = log_file or Path("data/logs/bot.log")
    log_file.parent.mkdir(parents=True, exist_ok=True)

    handlers: list[logging.Handler] = [RichHandler(rich_tracebacks=True, show_path=False)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        handlers=handlers,
    )

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
