"""Unit tests for BOS / CHoCH structure break detection.

Write-first (TDD): these tests must FAIL before src/engine/bos_choch.py exists.
Checkpoint: pytest tests/unit/test_engine_bos_choch.py — all must pass after T011.
"""

import pandas as pd
import pytest
from datetime import datetime, timedelta

from src.engine.models import SignalType, SwingPoint
from src.engine.bos_choch import detect_structure_break


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _df(closes: list, highs: list | None = None, lows: list | None = None) -> pd.DataFrame:
    """Build OHLCV DataFrame. highs/lows default to close ± 0.50."""
    n = len(closes)
    if highs is None:
        highs = [c + 0.5 for c in closes]
    if lows is None:
        lows = [c - 0.5 for c in closes]
    return pd.DataFrame({
        "time": [datetime(2024, 1, 1) + timedelta(hours=i) for i in range(n)],
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "tick_volume": [100] * n,
    })


def _sw(price, index, swing_type):
    return SwingPoint(price=price, candle_index=index, type=swing_type, confirmed=True, fractal_n=2)


# ---------------------------------------------------------------------------
# BOS — continuation signals
# ---------------------------------------------------------------------------

def test_bos_bullish_close_through_swing_high():
    """Last close > most recent swing HIGH with no established trend → BOS_BULLISH."""
    closes = [1900, 1901, 1902, 1901, 1900, 1912]
    swings = [_sw(1905.0, 2, "HIGH"), _sw(1898.0, 1, "LOW")]

    signal, level = detect_structure_break(_df(closes), swings)

    assert signal == SignalType.BOS_BULLISH
    assert level == 1905.0


def test_bos_bearish_close_through_swing_low():
    """Last close < most recent swing LOW with no established trend → BOS_BEARISH."""
    closes = [1910, 1909, 1908, 1909, 1910, 1888]
    swings = [_sw(1920.0, 2, "HIGH"), _sw(1895.0, 1, "LOW")]

    signal, level = detect_structure_break(_df(closes), swings)

    assert signal == SignalType.BOS_BEARISH
    assert level == 1895.0


# ---------------------------------------------------------------------------
# Candle-close rule (FR-004) — wicks must never trigger
# ---------------------------------------------------------------------------

def test_wick_above_swing_high_does_not_trigger_bos():
    """Wick exceeds swing HIGH but CLOSE stays below → NONE (FR-004)."""
    closes = [1900, 1901, 1902, 1901, 1900, 1903]
    highs  = [1901, 1902, 1903, 1902, 1901, 1915]  # last candle wick = 1915 > 1905
    lows   = [1899, 1900, 1901, 1900, 1899, 1899]
    swings = [_sw(1905.0, 2, "HIGH"), _sw(1898.0, 1, "LOW")]

    signal, level = detect_structure_break(_df(closes, highs, lows), swings)

    assert signal == SignalType.NONE
    assert level is None


def test_wick_below_swing_low_does_not_trigger_bos():
    """Wick breaks below swing LOW but CLOSE stays above → NONE (FR-004)."""
    closes = [1910, 1909, 1908, 1909, 1910, 1897]
    highs  = [1911, 1910, 1909, 1910, 1911, 1911]
    lows   = [1909, 1908, 1907, 1908, 1909, 1885]  # last candle wick = 1885 < 1895
    swings = [_sw(1920.0, 2, "HIGH"), _sw(1895.0, 1, "LOW")]

    signal, level = detect_structure_break(_df(closes, highs, lows), swings)

    assert signal == SignalType.NONE
    assert level is None


# ---------------------------------------------------------------------------
# CHoCH — reversal signals (D-006)
# ---------------------------------------------------------------------------

def test_choch_bearish_in_established_bullish_trend():
    """Close below swing LOW in established bullish trend (HH+HL) → CHoCH_BEARISH."""
    closes = [1900, 1905, 1903, 1910, 1908, 1885]
    # Established bullish: higher highs (1905→1910), higher lows (1900→1903)
    swings = [
        _sw(1905.0, 1, "HIGH"),
        _sw(1900.0, 0, "LOW"),
        _sw(1910.0, 3, "HIGH"),  # higher high
        _sw(1903.0, 2, "LOW"),   # higher low → most recent low, gets broken
    ]

    signal, level = detect_structure_break(_df(closes), swings)

    assert signal == SignalType.CHOCH_BEARISH
    assert level == 1903.0


def test_choch_bullish_in_established_bearish_trend():
    """Close above swing HIGH in established bearish trend (LH+LL) → CHoCH_BULLISH."""
    closes = [1910, 1905, 1907, 1900, 1902, 1925]
    # Established bearish: lower highs (1910→1907), lower lows (1905→1900)
    swings = [
        _sw(1910.0, 0, "HIGH"),
        _sw(1905.0, 1, "LOW"),
        _sw(1907.0, 2, "HIGH"),  # lower high → most recent high, gets broken
        _sw(1900.0, 3, "LOW"),   # lower low
    ]

    signal, level = detect_structure_break(_df(closes), swings)

    assert signal == SignalType.CHOCH_BULLISH
    assert level == 1907.0


# ---------------------------------------------------------------------------
# Ranging market → NONE
# ---------------------------------------------------------------------------

def test_no_swing_points_returns_none():
    """Empty swing_points → NONE signal."""
    closes = [1900, 1901, 1902, 1901, 1900]

    signal, level = detect_structure_break(_df(closes), [])

    assert signal == SignalType.NONE
    assert level is None


def test_close_does_not_break_any_level():
    """Close sits between swing HIGH and LOW → no break → NONE."""
    closes = [1900, 1901, 1902, 1901, 1901]   # last close 1901, swing high 1905, swing low 1898
    swings = [_sw(1905.0, 2, "HIGH"), _sw(1898.0, 1, "LOW")]

    signal, level = detect_structure_break(_df(closes), swings)

    assert signal == SignalType.NONE
    assert level is None


def test_only_swing_highs_no_break():
    """Only swing HIGH present, close below it → NONE."""
    closes = [1900, 1901, 1902, 1901, 1900]
    swings = [_sw(1905.0, 2, "HIGH")]

    signal, level = detect_structure_break(_df(closes), swings)

    assert signal == SignalType.NONE
    assert level is None


# ---------------------------------------------------------------------------
# Return type contract
# ---------------------------------------------------------------------------

def test_return_type_is_tuple_signal_and_optional_float():
    """Return type must be tuple[SignalType, float | None]."""
    signal, level = detect_structure_break(_df([1900, 1901, 1902]), [])

    assert isinstance(signal, SignalType)
    assert level is None or isinstance(level, float)


def test_bos_bullish_returns_broken_level_price():
    """Broken level price in return value must equal the swing HIGH price."""
    closes = [1900, 1901, 1900, 1901, 1900, 1912]
    swings = [_sw(1906.0, 2, "HIGH"), _sw(1898.0, 1, "LOW")]

    _, level = detect_structure_break(_df(closes), swings)

    assert level == 1906.0
