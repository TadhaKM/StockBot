"""Tests for core data models."""
import sys
import pytest

sys.path.insert(0, ".")

from src.models.market import Market, MarketOutcome, Platform
from src.models.prediction import Prediction
from src.models.position import Position, PositionSide


def make_binary_market(yes_prob: float = 0.6) -> Market:
    return Market(
        id="test-001",
        platform=Platform.POLYMARKET,
        question="Test question?",
        outcomes=[
            MarketOutcome(id="yes", name="YES", probability=yes_prob, price=yes_prob, volume=100_000),
            MarketOutcome(id="no",  name="NO",  probability=1 - yes_prob, price=1 - yes_prob, volume=100_000),
        ],
        volume_usd=200_000,
        liquidity_usd=50_000,
    )


def test_market_is_binary():
    m = make_binary_market()
    assert m.is_binary is True


def test_market_yes_probability():
    m = make_binary_market(yes_prob=0.65)
    assert m.yes_probability == pytest.approx(0.65)


def test_prediction_edge_calculated():
    pred = Prediction(
        market_id="test-001",
        our_probability=0.70,
        market_probability=0.55,
    )
    assert pred.edge == pytest.approx(0.15)
    assert pred.recommended_side == "yes"


def test_prediction_no_edge():
    pred = Prediction(
        market_id="test-001",
        our_probability=0.40,
        market_probability=0.55,
    )
    assert pred.edge == pytest.approx(-0.15)
    assert pred.recommended_side == "no"


def test_position_pnl():
    pos = Position(
        id="pos-001",
        market_id="test-001",
        platform="polymarket",
        side=PositionSide.YES,
        contracts=100,
        avg_entry_price=0.55,
        current_price=0.65,
    )
    assert pos.cost_basis == pytest.approx(55.0)
    assert pos.market_value == pytest.approx(65.0)
    assert pos.unrealized_pnl == pytest.approx(10.0)
