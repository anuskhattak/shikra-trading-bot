"""Unit tests for src/risk/recovery_mode.py — spec003 FR-023 to FR-028.

TDD: all tests written BEFORE implementation; they must FAIL until T012 is complete.
Run: pytest tests/unit/test_risk_recovery_mode.py
"""
from types import SimpleNamespace

import pytest

from src.risk.recovery_mode import (
    apply_recovery_lot,
    check_recovery_status,
    is_signal_allowed_in_recovery,
    update_recovery_profit,
)
from src.risk.models import RiskState


def _cfg(
    max_consecutive_losses: int = 3,
    recovery_lot_multiplier: float = 0.5,
    recovery_min_confidence: float = 0.80,
    recovery_profit_target_pips: float = 50.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        max_consecutive_losses=max_consecutive_losses,
        recovery_lot_multiplier=recovery_lot_multiplier,
        recovery_min_confidence=recovery_min_confidence,
        recovery_profit_target_pips=recovery_profit_target_pips,
    )


def _state(**kwargs) -> RiskState:
    defaults = dict(
        day_start_equity=10_000.0,
        consecutive_losses=0,
        in_recovery_mode=False,
        recovery_profit_pips=0.0,
    )
    defaults.update(kwargs)
    return RiskState(**defaults)


# ---------------------------------------------------------------------------
# T011 — US5: Recovery mode (FR-023 to FR-028)
# ---------------------------------------------------------------------------


def test_recovery_activates_at_loss_threshold():
    """FR-023/SC-004: consecutive_losses=3, max=3 → in_recovery_mode=True."""
    state = _state(consecutive_losses=3)
    new_state = check_recovery_status(state, _cfg(max_consecutive_losses=3))
    assert new_state.in_recovery_mode is True


def test_recovery_not_active_below_threshold():
    """FR-023: consecutive_losses=2, max=3 → in_recovery_mode=False."""
    state = _state(consecutive_losses=2)
    new_state = check_recovery_status(state, _cfg(max_consecutive_losses=3))
    assert new_state.in_recovery_mode is False


def test_recovery_lot_reduced():
    """FR-024/SC-004: normal_lot=0.10, multiplier=0.5 → result=0.05."""
    result = apply_recovery_lot(lot_size=0.10, recovery_lot_multiplier=0.5)
    assert result == pytest.approx(0.05)


def test_signal_rejected_in_recovery_low_confidence():
    """FR-025/SC-005: confidence=0.75, min=0.80 → False."""
    assert is_signal_allowed_in_recovery(confidence=0.75, recovery_min_confidence=0.80) is False


def test_signal_allowed_in_recovery_high_confidence():
    """FR-025: confidence=0.82, min=0.80 → True."""
    assert is_signal_allowed_in_recovery(confidence=0.82, recovery_min_confidence=0.80) is True


def test_recovery_exits_at_profit_target():
    """FR-026: recovery_profit_pips=50, target=50 → in_recovery_mode=False."""
    state = _state(in_recovery_mode=True, recovery_profit_pips=50.0)
    new_state = check_recovery_status(state, _cfg(recovery_profit_target_pips=50.0))
    assert new_state.in_recovery_mode is False


def test_recovery_profit_accumulated():
    """FR-026/FR-028: update_recovery_profit increments recovery_profit_pips."""
    state = _state(in_recovery_mode=True, recovery_profit_pips=20.0)
    new_state = update_recovery_profit(state, pips_gained_price_units=15.0)
    assert new_state.recovery_profit_pips == pytest.approx(35.0)
