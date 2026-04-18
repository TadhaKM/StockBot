"""Tests for the deterministic risk validation system."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from scripts.validate_risk import RiskVerdict, validate_risk
from src.risk.kelly import kelly_fraction, kelly_size


# ── Helpers ──────────────────────────────────────────────────────────────────

def _clean() -> dict:
    """Parameters that pass every gate."""
    return dict(
        p_model=0.65,
        p_market=0.50,
        confidence=0.72,
        bankroll=10_000.0,
        total_exposure_fraction=0.10,
        daily_loss_fraction=0.02,
        drawdown_fraction=0.03,
    )


# ── RiskVerdict type ─────────────────────────────────────────────────────────

class TestRiskVerdictType:
    def test_allowed_has_no_reasons(self):
        v = validate_risk(**_clean())
        assert v.allowed is True
        assert v.reasons == []

    def test_blocked_has_reasons(self):
        params = _clean()
        params["p_model"] = 0.51   # edge 0.01 < min 0.05
        params["confidence"] = 0.30
        v = validate_risk(**params)
        assert v.allowed is False
        assert len(v.reasons) >= 2

    def test_returns_verdict_instance(self):
        v = validate_risk(**_clean())
        assert isinstance(v, RiskVerdict)

    def test_gates_list_has_five_entries(self):
        v = validate_risk(**_clean())
        # Edge, Confidence, Exposure, Daily loss, Drawdown, Kelly -> 6
        assert len(v.gates) == 6

    def test_size_zero_when_blocked(self):
        params = _clean()
        params["p_model"] = 0.51  # fails edge
        v = validate_risk(**params)
        assert v.allowed is False
        assert v.position_size_usd == 0.0


# ── Gate 1: Edge ─────────────────────────────────────────────────────────────

class TestEdgeGate:
    def test_passes_when_edge_above_min(self):
        v = validate_risk(**_clean())  # edge = 0.15
        assert v.allowed is True
        edge_gate = v.gates[0]
        assert edge_gate[1] is True

    def test_fails_when_edge_below_min(self):
        params = _clean()
        params["p_model"] = 0.52   # edge = 0.02 < min_edge 0.05
        v = validate_risk(**params)
        assert any("edge" in r for r in v.reasons)
        assert v.gates[0][1] is False

    def test_fails_at_exactly_zero_edge(self):
        params = _clean()
        params["p_model"] = 0.50   # edge = 0.0
        v = validate_risk(**params)
        assert any("edge" in r for r in v.reasons)

    def test_negative_edge_uses_abs_value(self):
        """A trade on the NO side with sufficient |edge| should pass the edge gate."""
        params = _clean()
        params["p_model"] = 0.35   # edge = -0.15, |edge| = 0.15 > 0.05
        v = validate_risk(**params)
        assert v.gates[0][1] is True


# ── Gate 2: Confidence ───────────────────────────────────────────────────────

class TestConfidenceGate:
    def test_passes_at_threshold(self):
        params = _clean()
        params["confidence"] = 0.60   # exactly at min
        v = validate_risk(**params)
        assert v.gates[1][1] is True

    def test_fails_below_threshold(self):
        params = _clean()
        params["confidence"] = 0.59
        v = validate_risk(**params)
        assert v.gates[1][1] is False
        assert any("confidence" in r for r in v.reasons)

    def test_confidence_failure_collected_alongside_other_failures(self):
        params = _clean()
        params["confidence"] = 0.40
        params["p_model"] = 0.52   # also fails edge
        v = validate_risk(**params)
        assert any("confidence" in r for r in v.reasons)
        assert any("edge" in r for r in v.reasons)
        assert len(v.reasons) >= 2


# ── Gate 3a: Exposure ─────────────────────────────────────────────────────────

class TestExposureGate:
    def test_passes_below_limit(self):
        params = _clean()
        params["total_exposure_fraction"] = 0.19   # limit = 0.20
        v = validate_risk(**params)
        assert v.gates[2][1] is True

    def test_fails_at_limit(self):
        params = _clean()
        params["total_exposure_fraction"] = 0.20   # exactly at limit: fail (>= check)
        v = validate_risk(**params)
        assert v.gates[2][1] is False
        assert any("exposure" in r for r in v.reasons)

    def test_fails_above_limit(self):
        params = _clean()
        params["total_exposure_fraction"] = 0.25
        v = validate_risk(**params)
        assert v.gates[2][1] is False


# ── Gate 3b: Daily loss ───────────────────────────────────────────────────────

class TestDailyLossGate:
    def test_passes_below_limit(self):
        params = _clean()
        params["daily_loss_fraction"] = 0.09   # limit = 0.10
        v = validate_risk(**params)
        assert v.gates[3][1] is True

    def test_fails_at_limit(self):
        params = _clean()
        params["daily_loss_fraction"] = 0.10
        v = validate_risk(**params)
        assert v.gates[3][1] is False
        assert any("daily_loss" in r for r in v.reasons)


# ── Gate 3c: Drawdown ─────────────────────────────────────────────────────────

class TestDrawdownGate:
    def test_passes_below_limit(self):
        params = _clean()
        params["drawdown_fraction"] = 0.07   # limit = 0.08
        v = validate_risk(**params)
        assert v.gates[4][1] is True

    def test_fails_at_limit(self):
        params = _clean()
        params["drawdown_fraction"] = 0.08
        v = validate_risk(**params)
        assert v.gates[4][1] is False
        assert any("drawdown" in r for r in v.reasons)


# ── Gate 4: Kelly sizing ──────────────────────────────────────────────────────

class TestKellySizingGate:
    def test_size_positive_when_all_pass(self):
        v = validate_risk(**_clean())
        assert v.position_size_usd > 0.0

    def test_size_respects_max_position_cap(self):
        # Even huge edge should be capped at max_position_size (5% of bankroll)
        params = _clean()
        params["p_model"] = 0.95
        params["p_market"] = 0.10
        params["bankroll"] = 10_000.0
        v = validate_risk(**params)
        assert v.position_size_usd <= 10_000.0 * 0.05 + 0.01  # allow rounding

    def test_size_scales_with_bankroll(self):
        v1 = validate_risk(**{**_clean(), "bankroll": 5_000.0})
        v2 = validate_risk(**{**_clean(), "bankroll": 10_000.0})
        assert v2.position_size_usd == pytest.approx(v1.position_size_usd * 2, abs=1.0)

    def test_no_edge_size_is_zero(self):
        params = _clean()
        params["p_model"] = 0.50  # zero edge -- Kelly returns 0
        v = validate_risk(**params)
        assert v.position_size_usd == 0.0


# ── All-gates-fail scenario ───────────────────────────────────────────────────

class TestAllGatesFail:
    def test_collects_every_reason(self):
        v = validate_risk(
            p_model=0.52,       # edge 0.02 < 0.05 -- fails edge
            p_market=0.50,
            confidence=0.40,    # < 0.60 -- fails confidence
            bankroll=10_000.0,
            total_exposure_fraction=0.25,   # >= 0.20 -- fails exposure
            daily_loss_fraction=0.15,       # >= 0.10 -- fails daily loss
            drawdown_fraction=0.10,         # >= 0.08 -- fails drawdown
        )
        assert v.allowed is False
        assert len(v.reasons) == 5
        assert any("edge" in r for r in v.reasons)
        assert any("confidence" in r for r in v.reasons)
        assert any("exposure" in r for r in v.reasons)
        assert any("daily_loss" in r for r in v.reasons)
        assert any("drawdown" in r for r in v.reasons)

    def test_all_gates_reported_even_when_all_fail(self):
        v = validate_risk(
            p_model=0.52, p_market=0.50, confidence=0.40,
            bankroll=10_000.0,
            total_exposure_fraction=0.25,
            daily_loss_fraction=0.15,
            drawdown_fraction=0.10,
        )
        assert len(v.gates) == 6
        # First 5 gates should all have failed
        for label, passed, _ in v.gates[:5]:
            assert passed is False, f"Expected {label} to fail"
