"""Tests for RiskManager gating logic."""
import sys
import pytest

sys.path.insert(0, ".")

from src.models import Prediction
from src.models.position import Position, PositionSide
from src.risk.manager import RiskManager


def make_prediction(our_prob: float = 0.65, market_prob: float = 0.55) -> Prediction:
    return Prediction(
        market_id="mkt-001",
        our_probability=our_prob,
        market_probability=market_prob,
        confidence=0.7,
    )


def test_approves_good_trade():
    rm = RiskManager(bankroll=10_000)
    d = rm.evaluate(make_prediction(our_prob=0.70, market_prob=0.55))
    assert d.approved is True
    assert d.size_usd > 0


def test_rejects_insufficient_edge():
    rm = RiskManager(bankroll=10_000)
    d = rm.evaluate(make_prediction(our_prob=0.57, market_prob=0.55))
    assert d.approved is False
    assert "edge" in d.reason.lower()


def test_rejects_max_positions():
    positions = [
        Position(
            id=f"pos-{i}",
            market_id=f"mkt-{i:03}",
            platform="polymarket",
            side=PositionSide.YES,
            contracts=10,
            avg_entry_price=0.5,
            current_price=0.5,
        )
        for i in range(10)   # fill up to max
    ]
    rm = RiskManager(bankroll=10_000, open_positions=positions)
    d = rm.evaluate(make_prediction())
    assert d.approved is False
    assert "positions" in d.reason.lower()


def test_rejects_duplicate_position():
    pos = Position(
        id="pos-dup",
        market_id="mkt-001",   # same as prediction
        platform="polymarket",
        side=PositionSide.YES,
        contracts=10,
        avg_entry_price=0.5,
        current_price=0.5,
    )
    rm = RiskManager(bankroll=10_000, open_positions=[pos])
    d = rm.evaluate(make_prediction())
    assert d.approved is False
    assert "already holding" in d.reason.lower()
