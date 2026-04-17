"""Tests for Kelly criterion sizing."""
import pytest
import sys

sys.path.insert(0, ".")

from src.risk.kelly import kelly_fraction, kelly_size


def test_positive_edge():
    frac = kelly_fraction(our_prob=0.65, market_price=0.55)
    assert frac > 0, "Positive edge should produce positive Kelly fraction"


def test_no_edge():
    frac = kelly_fraction(our_prob=0.55, market_price=0.55)
    assert frac == 0.0, "Zero edge should produce zero Kelly fraction"


def test_negative_edge():
    frac = kelly_fraction(our_prob=0.40, market_price=0.55)
    assert frac == 0.0, "Negative edge should produce zero Kelly fraction"


def test_fractional_kelly():
    full = kelly_fraction(0.65, 0.55, fractional=1.0)
    quarter = kelly_fraction(0.65, 0.55, fractional=0.25)
    assert abs(quarter - full * 0.25) < 1e-9


def test_kelly_size_capped():
    # Should never exceed max_fraction regardless of edge
    size = kelly_size(10_000, our_prob=0.99, market_price=0.01, max_fraction=0.05)
    assert size <= 10_000 * 0.05 + 0.01, "Size must respect max_fraction cap"


def test_invalid_price():
    assert kelly_fraction(0.7, 0.0) == 0.0
    assert kelly_fraction(0.7, 1.0) == 0.0


def test_kelly_size_zero_on_no_edge():
    size = kelly_size(10_000, our_prob=0.50, market_price=0.50)
    assert size == 0.0
