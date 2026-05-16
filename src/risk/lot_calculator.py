"""Lot sizing and SL/TP price calculation — spec003 FR-001 to FR-011.

All functions are pure (NFR-002): same inputs always produce same outputs.
No MT5 import (NFR-001). No global state (NFR-003).
"""
from __future__ import annotations

from src.engine.models import Direction

# XAUUSD contract constant: 1 standard lot = 100 oz; 1 pip = $0.10/oz × 100 oz = $10.
# This is a broker/symbol spec, not a user preference — not in config (plan D-004).
XAUUSD_PIP_VALUE: float = 10.0


def calculate_lot_size(
    balance: float,
    risk_percent: float,
    sl_distance: float,
    pip_value_per_lot: float = XAUUSD_PIP_VALUE,
    max_lot: float = 5.0,
    min_lot: float = 0.01,
) -> float:
    """Return lot size so that max loss == balance × risk_percent% if SL is hit.

    Order of operations (D-007): raw lot → 5% hard cap → clamp to [min_lot, max_lot].
    sl_distance is in price units (same unit as D1_ATR, e.g. 30.0 = $30 move).
    """
    risk_amount = balance * (risk_percent / 100.0)

    # 5% hard cap: risk may never exceed 5% of account balance (FR-004)
    max_risk = balance * 0.05
    if risk_amount > max_risk:
        risk_amount = max_risk

    raw_lot = risk_amount / (sl_distance * pip_value_per_lot)
    lot = round(raw_lot, 2)

    # Clamp to broker limits (FR-002, FR-003)
    return max(min_lot, min(lot, max_lot))


def calculate_sl_price(
    entry: float,
    direction: Direction,
    d1_atr: float,
    sl_atr_multiplier: float = 1.5,
) -> float:
    """Return SL price = entry ± (D1_ATR × sl_atr_multiplier).

    LONG: SL below entry. SHORT: SL above entry.
    Raises ValueError if d1_atr <= 0 or entry <= 0 — caller must provide valid data (FR-006a).
    """
    if d1_atr <= 0:
        raise ValueError(f"d1_atr must be > 0, got {d1_atr}")
    if entry <= 0:
        raise ValueError(f"entry must be > 0, got {entry}")

    distance = _calculate_sl_distance(d1_atr, sl_atr_multiplier)
    if direction == Direction.LONG:
        return entry - distance
    return entry + distance


def _calculate_sl_distance(d1_atr: float, sl_atr_multiplier: float) -> float:
    """Return sl_distance = d1_atr × sl_atr_multiplier in price units (FR-007).

    Private helper — not part of the public API.
    """
    return d1_atr * sl_atr_multiplier


def calculate_tp_prices(
    entry: float,
    sl_price: float,
    direction: Direction,
    tp1_rr: float = 1.5,
    tp2_rr: float = 3.0,
) -> tuple[float, float]:
    """Return (tp1_price, tp2_price) based on SL distance and R:R ratios.

    LONG:  TP1 = entry + sl_distance × tp1_rr;  TP2 = entry + sl_distance × tp2_rr.
    SHORT: TP1 = entry − sl_distance × tp1_rr;  TP2 = entry − sl_distance × tp2_rr.
    Invariant: LONG → entry < tp1 < tp2; SHORT → tp2 < tp1 < entry (FR-011).
    """
    sl_distance = abs(entry - sl_price)
    if direction == Direction.LONG:
        tp1 = entry + sl_distance * tp1_rr
        tp2 = entry + sl_distance * tp2_rr
    else:
        tp1 = entry - sl_distance * tp1_rr
        tp2 = entry - sl_distance * tp2_rr
    return tp1, tp2
