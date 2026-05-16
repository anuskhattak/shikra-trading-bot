"""Unit tests for src/risk/lot_calculator.py — spec003 FR-001 to FR-011.

TDD: all tests written BEFORE implementation; they must FAIL until T006 is complete.
Run: pytest tests/unit/test_risk_lot_calculator.py
"""
import pytest

from src.risk.lot_calculator import (
    XAUUSD_PIP_VALUE,
    _calculate_sl_distance,
    calculate_lot_size,
    calculate_sl_price,
    calculate_tp_prices,
)
from src.engine.models import Direction


# ---------------------------------------------------------------------------
# T005 — US1: Lot size calculation (FR-001 to FR-005)
# ---------------------------------------------------------------------------


def test_lot_size_formula_correct():
    """SC-001: balance=10000, risk=1%, sl_distance=20 → lot = (10000*0.01)/(20*10) = 0.50."""
    result = calculate_lot_size(
        balance=10_000.0,
        risk_percent=1.0,
        sl_distance=20.0,
        pip_value_per_lot=XAUUSD_PIP_VALUE,
        max_lot=5.0,
        min_lot=0.01,
    )
    assert result == pytest.approx(0.50, abs=0.01)


def test_lot_size_clamped_to_minimum():
    """FR-002, SC-006: extremely wide SL → lot floored at 0.01."""
    result = calculate_lot_size(
        balance=100.0,
        risk_percent=1.0,
        sl_distance=10_000.0,  # enormous SL → raw lot < 0.01
        pip_value_per_lot=XAUUSD_PIP_VALUE,
        max_lot=5.0,
        min_lot=0.01,
    )
    assert result == 0.01


def test_lot_size_clamped_to_maximum():
    """FR-003, SC-006: large balance / tiny SL → lot capped at max_lot_size."""
    result = calculate_lot_size(
        balance=10_000_000.0,
        risk_percent=10.0,
        sl_distance=0.1,
        pip_value_per_lot=XAUUSD_PIP_VALUE,
        max_lot=5.0,
        min_lot=0.01,
    )
    assert result == 5.0


def test_hard_cap_5pct_applied():
    """FR-004: risk_amount > balance*0.05 → lot reduced so max loss ≤ 5% of balance."""
    # risk_percent=10% would risk $1,000 on a $10,000 account (>5%)
    result = calculate_lot_size(
        balance=10_000.0,
        risk_percent=10.0,
        sl_distance=20.0,
        pip_value_per_lot=XAUUSD_PIP_VALUE,
        max_lot=5.0,
        min_lot=0.01,
    )
    # max allowed risk = 10000 * 0.05 = 500; lot = 500 / (20 * 10) = 2.50
    max_loss = result * 20.0 * XAUUSD_PIP_VALUE
    assert max_loss <= 10_000.0 * 0.05 + 0.01  # small float tolerance


# ---------------------------------------------------------------------------
# T005b — US2: SL / TP price calculation (FR-006 to FR-011)
# ---------------------------------------------------------------------------


def test_sl_long_below_entry():
    """FR-006: LONG SL must be below entry price."""
    sl = calculate_sl_price(entry=2350.0, direction=Direction.LONG, d1_atr=20.0, sl_atr_multiplier=1.5)
    assert sl < 2350.0


def test_sl_short_above_entry():
    """FR-006, SC-007: SHORT SL must be above entry price."""
    sl = calculate_sl_price(entry=2350.0, direction=Direction.SHORT, d1_atr=20.0, sl_atr_multiplier=1.5)
    assert sl > 2350.0


def test_sl_raises_on_invalid_atr():
    """FR-006a: d1_atr <= 0 must raise ValueError — caller must provide valid ATR."""
    with pytest.raises(ValueError):
        calculate_sl_price(entry=2350.0, direction=Direction.LONG, d1_atr=0.0, sl_atr_multiplier=1.5)
    with pytest.raises(ValueError):
        calculate_sl_price(entry=2350.0, direction=Direction.LONG, d1_atr=-5.0, sl_atr_multiplier=1.5)


def test_sl_raises_on_invalid_entry():
    """FR-006a: entry <= 0 must raise ValueError."""
    with pytest.raises(ValueError):
        calculate_sl_price(entry=0.0, direction=Direction.LONG, d1_atr=20.0, sl_atr_multiplier=1.5)


def test_sl_uses_atr_multiplier():
    """FR-007: sl_distance = d1_atr × sl_atr_multiplier (in price units)."""
    distance = _calculate_sl_distance(d1_atr=20.0, sl_atr_multiplier=1.5)
    assert distance == pytest.approx(30.0)


def test_tp_long_prices_correct():
    """SC-003: LONG entry=2350, D1_ATR=20, mult=1.5 → SL=2320, TP1=2395, TP2=2440."""
    sl = calculate_sl_price(entry=2350.0, direction=Direction.LONG, d1_atr=20.0, sl_atr_multiplier=1.5)
    tp1, tp2 = calculate_tp_prices(
        entry=2350.0, sl_price=sl, direction=Direction.LONG, tp1_rr=1.5, tp2_rr=3.0
    )
    assert sl == pytest.approx(2320.0)
    assert tp1 == pytest.approx(2395.0)
    assert tp2 == pytest.approx(2440.0)


def test_tp_short_prices_correct():
    """FR-011, SC-007: SHORT SL above entry, both TPs below entry."""
    sl = calculate_sl_price(entry=2350.0, direction=Direction.SHORT, d1_atr=20.0, sl_atr_multiplier=1.5)
    tp1, tp2 = calculate_tp_prices(
        entry=2350.0, sl_price=sl, direction=Direction.SHORT, tp1_rr=1.5, tp2_rr=3.0
    )
    assert sl > 2350.0
    assert tp1 < 2350.0
    assert tp2 < tp1


def test_tp_ordering_long():
    """FR-011: LONG invariant — sl_price < entry < tp1 < tp2."""
    entry = 2350.0
    sl = calculate_sl_price(entry=entry, direction=Direction.LONG, d1_atr=20.0, sl_atr_multiplier=1.5)
    tp1, tp2 = calculate_tp_prices(entry=entry, sl_price=sl, direction=Direction.LONG, tp1_rr=1.5, tp2_rr=3.0)
    assert sl < entry < tp1 < tp2


def test_tp_ordering_short():
    """FR-011: SHORT invariant — tp2 < tp1 < entry < sl_price."""
    entry = 2350.0
    sl = calculate_sl_price(entry=entry, direction=Direction.SHORT, d1_atr=20.0, sl_atr_multiplier=1.5)
    tp1, tp2 = calculate_tp_prices(entry=entry, sl_price=sl, direction=Direction.SHORT, tp1_rr=1.5, tp2_rr=3.0)
    assert tp2 < tp1 < entry < sl
