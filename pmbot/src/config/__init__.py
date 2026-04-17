"""
Config loader: merges config/default.yaml with config/secrets.yaml (if present),
then overlays any environment variable overrides.

Usage:
    from src.config import cfg
    print(cfg.bot.trading_mode)
    print(cfg.risk.max_bankroll_fraction)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


# ── Schema ────────────────────────────────────────────────────────────────────

class BotConfig(BaseModel):
    name: str = "pmbot"
    version: str = "0.1.0"
    trading_mode: str = "paper"
    cycle_interval_minutes: int = 15

    @property
    def is_paper(self) -> bool:
        return self.trading_mode == "paper"


class PlatformConfig(BaseModel):
    enabled: bool = True
    base_url: str = ""
    demo_url: str = ""


class PlatformsConfig(BaseModel):
    polymarket: PlatformConfig = Field(default_factory=PlatformConfig)
    kalshi: PlatformConfig = Field(default_factory=PlatformConfig)


class ScannerConfig(BaseModel):
    min_volume_usd: float = 1_000
    min_liquidity_usd: float = 500
    max_days_to_close: float = 90


class FilterConfig(BaseModel):
    min_market_probability: float = 0.05
    max_market_probability: float = 0.95
    required_categories: list[str] = Field(default_factory=list)
    blocked_categories: list[str] = Field(default_factory=list)


class PredictionConfig(BaseModel):
    model: str = "baseline"
    min_confidence: float = 0.4


class RiskConfig(BaseModel):
    bankroll_usd: float = 10_000.0
    max_bankroll_fraction: float = 0.05
    max_open_positions: int = 10
    min_edge_threshold: float = 0.03
    kelly_fraction: float = 0.25


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "data/logs/bot.log"
    json: bool = False


class Config(BaseModel):
    bot: BotConfig = Field(default_factory=BotConfig)
    platforms: PlatformsConfig = Field(default_factory=PlatformsConfig)
    scanner: ScannerConfig = Field(default_factory=ScannerConfig)
    filter: FilterConfig = Field(default_factory=FilterConfig)
    prediction: PredictionConfig = Field(default_factory=PredictionConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    # Secrets (loaded from secrets.yaml, never from default.yaml)
    secrets: dict[str, Any] = Field(default_factory=dict)


# ── Loader ────────────────────────────────────────────────────────────────────

def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning new dict."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _apply_env_overrides(data: dict) -> dict:
    """
    Apply environment variable overrides.
    Convention: PMBOT__RISK__MAX_BANKROLL_FRACTION=0.02
    Maps to data["risk"]["max_bankroll_fraction"] = 0.02
    """
    for key, val in os.environ.items():
        if not key.startswith("PMBOT__"):
            continue
        parts = key.removeprefix("PMBOT__").lower().split("__")
        node = data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        # Best-effort type coercion
        leaf = parts[-1]
        existing = node.get(leaf)
        if isinstance(existing, bool):
            node[leaf] = val.lower() in ("1", "true", "yes")
        elif isinstance(existing, float):
            node[leaf] = float(val)
        elif isinstance(existing, int):
            node[leaf] = int(val)
        else:
            node[leaf] = val
    return data


def load_config(
    default_path: Path | str = "config/default.yaml",
    secrets_path: Path | str = "config/secrets.yaml",
) -> Config:
    default_path = Path(default_path)
    secrets_path = Path(secrets_path)

    with default_path.open(encoding="utf-8") as f:
        data: dict = yaml.safe_load(f) or {}

    if secrets_path.exists():
        with secrets_path.open(encoding="utf-8") as f:
            secrets: dict = yaml.safe_load(f) or {}
        data["secrets"] = secrets
    else:
        data["secrets"] = {}

    data = _apply_env_overrides(data)
    return Config.model_validate(data)


# Singleton — import this everywhere
cfg = load_config()
