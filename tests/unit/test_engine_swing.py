"""Unit tests for fractal swing point detection.

Write-first (TDD): these tests must FAIL before src/engine/swing.py exists.
Checkpoint: pytest tests/unit/test_engine_swing.py — all must pass after T010.
"""

import pandas as pd
import pytest
from datetime import datetime, timedelta

from src.engine.models import SwingPoint
from src.engine.swing import detect_swing_points


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _df(highs: list, lows: list, closes: list | None = None) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame from high/low arrays."""
    n = len(highs)
    if closes is None:
        closes = [(h + l) / 2 for h, l in zip(highs, lows)]
    return pd.DataFrame({
        "time": [datetime(2024, 1, 1) + timedelta(hours=i) for i in range(n)],
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "tick_volume": [100] * n,
    })


def _swing(price, index, swing_type):
    return SwingPoint(price=price, candle_index=index, type=swing_type, confirmed=True, fractal_n=2)


# ---------------------------------------------------------------------------
# Confirmed pivot detection
# ---------------------------------------------------------------------------

def test_swing_high_confirmed():
    """Peak with fractal_n=2 strictly lower highs on each side → confirmed HIGH."""
    #               0     1     2     3     4     5     6     7     8     9
    highs = [1900, 1901, 1902, 1903, 1904, 1910, 1904, 1903, 1902, 1901]
    lows  = [1895, 1896, 1897, 1898, 1899, 1900, 1899, 1898, 1897, 1896]
    result = detect_swing_points(_df(highs, lows), fractal_n=2, lookback=len(highs))

    swing_highs = [s for s in result if s.type == "HIGH"]
    assert len(swing_highs) >= 1
    peak = max(swing_highs, key=lambda s: s.price)
    assert peak.price == 1910
    assert peak.confirmed is True
    assert peak.candle_index == 5


def test_swing_low_confirmed():
    """Trough with fractal_n=2 strictly higher lows on each side → confirmed LOW."""
    highs = [1910, 1909, 1908, 1907, 1906, 1905, 1906, 1907, 1908, 1909]
    lows  = [1905, 1904, 1903, 1902, 1901, 1895, 1901, 1902, 1903, 1904]
    result = detect_swing_points(_df(highs, lows), fractal_n=2, lookback=len(highs))

    swing_lows = [s for s in result if s.type == "LOW"]
    assert len(swing_lows) >= 1
    trough = min(swing_lows, key=lambda s: s.price)
    assert trough.price == 1895
    assert trough.confirmed is True
    assert trough.candle_index == 5


def test_fractal_n_1_works():
    """fractal_n=1 requires only 1 candle on each side — narrower confirmation window."""
    highs = [1900, 1910, 1900, 1901, 1902]
    lows  = [1895, 1895, 1895, 1895, 1895]
    result = detect_swing_points(_df(highs, lows), fractal_n=1, lookback=len(highs))

    swing_highs = [s for s in result if s.type == "HIGH"]
    assert any(s.candle_index == 1 and s.price == 1910 for s in swing_highs)


# ---------------------------------------------------------------------------
# Unconfirmed / edge cases
# ---------------------------------------------------------------------------

def test_last_fractal_n_rows_excluded():
    """A pivot in the last fractal_n rows cannot be confirmed — must be absent."""
    highs = [1900, 1901, 1902, 1903, 1910]  # potential high at index 4 (last row)
    lows  = [1895, 1896, 1897, 1898, 1899]
    result = detect_swing_points(_df(highs, lows), fractal_n=2, lookback=len(highs))

    assert not any(s.candle_index == 4 for s in result)


def test_too_few_candles_returns_empty():
    """Fewer candles than 2*fractal_n+1 → cannot satisfy fractal rule → empty list."""
    highs = [1900, 1905, 1900]   # 3 candles, fractal_n=2 needs ≥ 5
    lows  = [1895, 1895, 1895]
    result = detect_swing_points(_df(highs, lows), fractal_n=2, lookback=len(highs))

    assert result == []


def test_flat_market_no_pivots():
    """All candles at identical high/low → strict inequality fails → no pivots."""
    highs = [1900.0] * 10
    lows  = [1895.0] * 10
    result = detect_swing_points(_df(highs, lows), fractal_n=2, lookback=len(highs))

    assert result == []


def test_equal_adjacent_high_not_a_pivot():
    """Adjacent candle has equal high → strict < fails → NOT a confirmed swing high."""
    #         0     1     2     3     4
    highs = [1900, 1905, 1905, 1903, 1902]   # index 1 and 2 tie — neither is strict peak
    lows  = [1895, 1898, 1898, 1896, 1895]
    result = detect_swing_points(_df(highs, lows), fractal_n=2, lookback=len(highs))

    swing_highs = [s for s in result if s.type == "HIGH"]
    assert not any(s.candle_index in (1, 2) for s in swing_highs)


# ---------------------------------------------------------------------------
# Lookback window
# ---------------------------------------------------------------------------

def test_lookback_limits_scan_window():
    """Pivot outside the lookback window must not appear in results."""
    #         0     1     2     3     4     5     6     7     8     9
    highs = [1900, 1901, 1910, 1901, 1900, 1901, 1902, 1901, 1900, 1901]
    lows  = [1895, 1896, 1897, 1896, 1895, 1896, 1897, 1896, 1895, 1896]

    full   = detect_swing_points(_df(highs, lows), fractal_n=2, lookback=len(highs))
    limited = detect_swing_points(_df(highs, lows), fractal_n=2, lookback=5)

    # Pivot at index 2 visible in full scan but not in limited (window = last 5 rows)
    assert any(s.candle_index == 2 for s in full)
    assert not any(s.candle_index == 2 for s in limited)


# ---------------------------------------------------------------------------
# Return type contract
# ---------------------------------------------------------------------------

def test_returns_list_of_confirmed_swing_points():
    """Output is always list[SwingPoint]; every item has confirmed=True."""
    highs = [1900, 1901, 1902, 1903, 1904, 1910, 1904, 1903, 1902, 1901]
    lows  = [1895, 1896, 1897, 1898, 1899, 1900, 1899, 1898, 1897, 1896]
    result = detect_swing_points(_df(highs, lows), fractal_n=2, lookback=len(highs))

    assert isinstance(result, list)
    assert all(isinstance(s, SwingPoint) for s in result)
    assert all(s.confirmed is True for s in result)


def test_empty_dataframe_returns_empty():
    """Empty DataFrame → empty list, no exception."""
    result = detect_swing_points(pd.DataFrame(columns=["time","open","high","low","close","tick_volume"]), fractal_n=2, lookback=20)
    assert result == []
