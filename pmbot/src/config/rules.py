"""
Config-driven trading rules engine.

All decision thresholds live in config/trading_rules.yaml.
Nothing is hardcoded — swap the YAML to change bot behaviour.

Usage:
    from src.config.rules import load_rules, validate_market_conditions, \
        validate_edge, validate_trade_allowed, BotState

    rules = load_rules()
    result = validate_market_conditions(market, rules)
    if not result.passed:
        print(result.failures)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from src.scanner.base import Market

_DEFAULT_RULES_PATH = Path("config/trading_rules.yaml")


# ── Rule schema (mirrors trading_rules.yaml) ──────────────────────────────────

class MarketRules(BaseModel):
    min_volume: float = 500
    max_spread: float = 0.03
    min_orderbook_depth: float = 100
    max_days_to_expiry: float = 30


class EdgeRules(BaseModel):
    min_edge: float = 0.05
    min_confidence: float = 0.6


class SizingRules(BaseModel):
    kelly_fraction: float = 0.25
    max_position_size: float = 0.05
    max_total_exposure: float = 0.2
    max_daily_loss: float = 0.1
    max_drawdown: float = 0.08


class ExecutionRules(BaseModel):
    max_slippage: float = 0.02


class TradingRules(BaseModel):
    market: MarketRules = Field(default_factory=MarketRules)
    edge: EdgeRules = Field(default_factory=EdgeRules)
    sizing: SizingRules = Field(default_factory=SizingRules)
    execution: ExecutionRules = Field(default_factory=ExecutionRules)


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class RuleResult:
    """Structured pass/fail with every reason a check failed."""
    passed: bool
    failures: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.passed

    @classmethod
    def ok(cls) -> "RuleResult":
        return cls(passed=True)

    @classmethod
    def fail(cls, *reasons: str) -> "RuleResult":
        return cls(passed=False, failures=list(reasons))


# ── Bot portfolio state (caller must populate each cycle) ─────────────────────

@dataclass
class BotState:
    """Snapshot of live portfolio used by validate_trade_allowed."""
    open_positions: int = 0
    total_exposure_fraction: float = 0.0   # deployed capital / bankroll
    daily_loss_fraction: float = 0.0       # today's realised loss / bankroll
    drawdown_fraction: float = 0.0         # loss from peak equity / peak equity


# ── Loader ────────────────────────────────────────────────────────────────────

def load_rules(path: Path | str = _DEFAULT_RULES_PATH) -> TradingRules:
    """
    Load and validate trading_rules.yaml.
    Missing keys fall back to TradingRules field defaults.
    """
    path = Path(path)
    if not path.exists():
        return TradingRules()
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return TradingRules.model_validate(data)


# ── Validators ────────────────────────────────────────────────────────────────

def validate_market_conditions(market: Market, rules: TradingRules) -> RuleResult:
    """
    Gate 1 — market quality.
    Checks volume, spread, orderbook depth, and days to expiry.
    Spread and depth checks are skipped when the scanner did not provide the data.
    """
    mr = rules.market
    failures: list[str] = []

    if market.volume_usd < mr.min_volume:
        failures.append(
            f"volume {market.volume_usd:.0f} < min {mr.min_volume:.0f}"
        )

    if market.spread is not None and market.spread > mr.max_spread:
        failures.append(
            f"spread {market.spread:.4f} > max {mr.max_spread:.4f}"
        )

    if market.orderbook_depth is not None and market.orderbook_depth < mr.min_orderbook_depth:
        failures.append(
            f"orderbook_depth {market.orderbook_depth:.0f} < min {mr.min_orderbook_depth:.0f}"
        )

    if market.days_to_close is not None and market.days_to_close > mr.max_days_to_expiry:
        failures.append(
            f"days_to_close {market.days_to_close:.1f} > max {mr.max_days_to_expiry:.1f}"
        )

    if failures:
        return RuleResult(passed=False, failures=failures)
    return RuleResult.ok()


def validate_edge(
    p_model: float,
    p_market: float,
    rules: TradingRules,
    *,
    confidence: float = 1.0,
) -> RuleResult:
    """
    Gate 2 — signal quality.
    Checks that the model's edge and confidence both clear their thresholds.

    Args:
        p_model:    model's estimated probability (0–1)
        p_market:   current market price / implied probability (0–1)
        rules:      TradingRules instance from load_rules()
        confidence: model confidence score (0–1); defaults to 1.0 (skip check)
    """
    er = rules.edge
    failures: list[str] = []

    edge = abs(p_model - p_market)
    if edge < er.min_edge:
        failures.append(
            f"edge {edge:.4f} < min {er.min_edge:.4f}"
        )

    if confidence < er.min_confidence:
        failures.append(
            f"confidence {confidence:.4f} < min {er.min_confidence:.4f}"
        )

    if failures:
        return RuleResult(passed=False, failures=failures)
    return RuleResult.ok()


def validate_trade_allowed(state: BotState, rules: TradingRules) -> RuleResult:
    """
    Gate 3 — portfolio-level risk limits.
    Checks total exposure, daily loss, and drawdown against sizing limits.
    Any breach blocks the trade; all breaches are reported together.

    Args:
        state: current BotState snapshot (caller must populate each cycle)
        rules: TradingRules instance from load_rules()
    """
    sr = rules.sizing
    failures: list[str] = []

    if state.total_exposure_fraction >= sr.max_total_exposure:
        failures.append(
            f"total_exposure {state.total_exposure_fraction:.2%} >= limit {sr.max_total_exposure:.2%}"
        )

    if state.daily_loss_fraction >= sr.max_daily_loss:
        failures.append(
            f"daily_loss {state.daily_loss_fraction:.2%} >= limit {sr.max_daily_loss:.2%} — trading halted"
        )

    if state.drawdown_fraction >= sr.max_drawdown:
        failures.append(
            f"drawdown {state.drawdown_fraction:.2%} >= limit {sr.max_drawdown:.2%} — trading halted"
        )

    if failures:
        return RuleResult(passed=False, failures=failures)
    return RuleResult.ok()
