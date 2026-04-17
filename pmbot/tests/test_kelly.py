"""Tests for Kelly criterion utilities."""
from __future__ import annotations

import pytest

from src.risk.kelly import kelly_fraction, kelly_size


class TestKellyFraction:
    def test_positive_edge(self):
        # p=0.6 on a binary market priced at 0.5 → b = (1-0.5)/0.5 = 1
        # f* = (0.6*1 - 0.4)/1 = 0.2
        frac = kelly_fraction(our_prob=0.6, market_prob=0.5)
        assert abs(frac - 0.2) < 1e-9

    def test_no_edge(self):
        frac = kelly_fraction(our_prob=0.5, market_prob=0.5)
        assert frac == pytest.approx(0.0)

    def test_negative_edge_clamped(self):
        frac = kelly_fraction(our_prob=0.3, market_prob=0.6)
        assert frac <= 0.0

    def test_fractional_kelly(self):
        full = kelly_fraction(our_prob=0.7, market_prob=0.5)
        half = kelly_fraction(our_prob=0.7, market_prob=0.5, fraction=0.5)
        assert abs(half - full * 0.5) < 1e-9

    def test_never_exceeds_one(self):
        frac = kelly_fraction(our_prob=0.99, market_prob=0.01, fraction=1.0)
        assert frac <= 1.0


class TestKellySize:
    def test_basic_sizing(self):
        size = kelly_size(
            our_prob=0.6,
            market_prob=0.5,
            bankroll=1000.0,
            max_fraction=0.25,
        )
        assert size > 0
        assert size <= 250.0  # capped at max_fraction * bankroll

    def test_zero_bankroll(self):
        size = kelly_size(our_prob=0.6, market_prob=0.5, bankroll=0.0)
        assert size == 0.0

    def test_no_edge_returns_zero(self):
        size = kelly_size(our_prob=0.5, market_prob=0.5, bankroll=1000.0)
        assert size == 0.0
