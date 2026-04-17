"""
Central configuration loaded from environment variables / .env file.
Uses pydantic-settings so every field is validated at startup.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Mode ──────────────────────────────────────────────────────────────────
    trading_mode: TradingMode = TradingMode.PAPER

    # ── Polymarket ────────────────────────────────────────────────────────────
    polymarket_api_key: str = ""
    polymarket_api_secret: str = ""
    polymarket_private_key: str = ""
    polymarket_base_url: str = "https://clob.polymarket.com"

    # ── Kalshi ────────────────────────────────────────────────────────────────
    kalshi_api_key: str = ""
    kalshi_api_secret: str = ""
    kalshi_base_url: str = "https://trading-api.kalshi.com/trade-api/v2"
    kalshi_demo_base_url: str = "https://demo-api.kalshi.co/trade-api/v2"

    # ── Research ──────────────────────────────────────────────────────────────
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    news_api_key: str = ""

    # ── Risk ──────────────────────────────────────────────────────────────────
    max_bankroll_fraction: float = Field(default=0.05, gt=0, le=1.0)
    max_open_positions: int = Field(default=10, gt=0)
    min_edge_threshold: float = Field(default=0.03, ge=0)
    kelly_fraction: float = Field(default=0.25, gt=0, le=1.0)

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_file: Path = Path("data/logs/bot.log")

    @field_validator("trading_mode", mode="before")
    @classmethod
    def lower_mode(cls, v: str) -> str:
        return v.lower() if isinstance(v, str) else v

    @property
    def is_paper(self) -> bool:
        return self.trading_mode == TradingMode.PAPER

    @property
    def kalshi_effective_url(self) -> str:
        """Return demo URL in paper mode, live URL otherwise."""
        return self.kalshi_demo_base_url if self.is_paper else self.kalshi_base_url


# Singleton — import this everywhere
settings = Settings()
