"""Integration tests for src/risk/risk_manager.py — spec003 Phase 6.

TDD: all tests written BEFORE implementation; they must FAIL until T014 is complete.
Run: pytest tests/integration/test_risk_pipeline.py
"""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.engine.models import Direction, EntrySignal
from src.risk.models import RiskState
from src.risk.risk_manager import evaluate_trade_risk


def _signal(
    direction: Direction = Direction.LONG,
    confidence: float = 0.85,
    entry_zone_top: float = 2360.0,
    entry_zone_bottom: float = 2340.0,
    reason: str = "test",
) -> EntrySignal:
    return EntrySignal(
        direction=direction,
        confidence=confidence,
        entry_zone_top=entry_zone_top,
        entry_zone_bottom=entry_zone_bottom,
        reason=reason,
    )


def _cfg(**overrides) -> SimpleNamespace:
    base = dict(
        risk_percent=1.0,
        max_lot_size=5.0,
        min_lot_size=0.01,
        pip_value_per_lot=10.0,
        sl_atr_multiplier=1.5,
        tp1_rr_ratio=1.5,
        tp2_rr_ratio=3.0,
        max_daily_drawdown=5.0,
        max_trades_per_day=5,
        max_trades_per_session=2,
        cooldown_after_sl_hours=2.0,
        max_consecutive_losses=3,
        recovery_lot_multiplier=0.5,
        recovery_min_confidence=0.80,
        recovery_profit_target_pips=50.0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _state(**overrides) -> RiskState:
    defaults = dict(day_start_equity=10_000.0)
    defaults.update(overrides)
    return RiskState(**defaults)


# ---------------------------------------------------------------------------
# T013 — Phase 6: Full pipeline integration (all user stories)
# ---------------------------------------------------------------------------


def test_full_evaluation_returns_risk_calculation():
    """Valid LONG signal → RiskCalculation with lot > 0 and correct types."""
    sig = _signal(direction=Direction.LONG)
    risk_calc, new_state = evaluate_trade_risk(
        entry_signal=sig,
        balance=10_000.0,
        current_equity=10_000.0,
        d1_atr=20.0,
        state=_state(),
        config=_cfg(),
    )
    assert risk_calc.lot_size > 0.0
    assert risk_calc.sl_price > 0.0
    assert risk_calc.tp1_price > 0.0
    assert risk_calc.tp2_price > 0.0
    assert isinstance(new_state, RiskState)


def test_none_signal_returns_zero_lot():
    """direction=NONE → lot_size=0.0, sl_price=0.0, tp prices=0.0."""
    sig = _signal(direction=Direction.NONE, entry_zone_top=0.0, entry_zone_bottom=0.0)
    risk_calc, _ = evaluate_trade_risk(
        entry_signal=sig,
        balance=10_000.0,
        current_equity=10_000.0,
        d1_atr=20.0,
        state=_state(),
        config=_cfg(),
    )
    assert risk_calc.lot_size == 0.0
    assert risk_calc.sl_price == 0.0
    assert risk_calc.tp1_price == 0.0
    assert risk_calc.tp2_price == 0.0


def test_recovery_mode_reduces_lot_in_pipeline():
    """consecutive_losses=3, max=3 → recovery active → lot halved end-to-end (SC-004)."""
    normal_calc, _ = evaluate_trade_risk(
        entry_signal=_signal(),
        balance=10_000.0,
        current_equity=10_000.0,
        d1_atr=20.0,
        state=_state(consecutive_losses=0),
        config=_cfg(),
    )
    recovery_calc, _ = evaluate_trade_risk(
        entry_signal=_signal(confidence=0.90),
        balance=10_000.0,
        current_equity=10_000.0,
        d1_atr=20.0,
        state=_state(consecutive_losses=3),
        config=_cfg(),
    )
    assert recovery_calc.lot_size < normal_calc.lot_size
    assert recovery_calc.in_recovery is True


def test_drawdown_block_returns_zero_lot():
    """Equity 6% below start, limit 5% → lot=0.0, reason populated."""
    sig = _signal()
    risk_calc, _ = evaluate_trade_risk(
        entry_signal=sig,
        balance=10_000.0,
        current_equity=9_400.0,   # 6% drawdown
        d1_atr=20.0,
        state=_state(day_start_equity=10_000.0),
        config=_cfg(max_daily_drawdown=5.0),
    )
    assert risk_calc.lot_size == 0.0
    assert risk_calc.reason != ""


def test_rr_ratios_correct_end_to_end():
    """SC-003: entry=2350, D1_ATR=20, mult=1.5 → SL=2320, TP1=2395, TP2=2440."""
    sig = _signal(
        direction=Direction.LONG,
        entry_zone_top=2360.0,    # midpoint = 2350
        entry_zone_bottom=2340.0,
    )
    risk_calc, _ = evaluate_trade_risk(
        entry_signal=sig,
        balance=10_000.0,
        current_equity=10_000.0,
        d1_atr=20.0,
        state=_state(),
        config=_cfg(sl_atr_multiplier=1.5, tp1_rr_ratio=1.5, tp2_rr_ratio=3.0),
    )
    assert risk_calc.sl_price == pytest.approx(2320.0)
    assert risk_calc.tp1_price == pytest.approx(2395.0)
    assert risk_calc.tp2_price == pytest.approx(2440.0)


def test_state_immutability():
    """Input RiskState must be unchanged after evaluate_trade_risk (NFR-003)."""
    original_state = _state(trades_today=2, consecutive_losses=1)
    state_copy = deepcopy(original_state)

    evaluate_trade_risk(
        entry_signal=_signal(),
        balance=10_000.0,
        current_equity=10_000.0,
        d1_atr=20.0,
        state=original_state,
        config=_cfg(),
    )
    assert original_state == state_copy
