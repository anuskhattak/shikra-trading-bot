"""Unit tests for FVG (Fair Value Gap) imbalance zone detection.

Write-first (TDD): these tests must FAIL before src/engine/fvg.py exists.
Checkpoint: pytest tests/unit/test_engine_fvg.py — all must pass after T013.
"""

import pandas as pd
import pytest
from datetime import datetime, timedelta

from src.engine.models import Direction, FVGStatus, FVGZone
from src.engine.fvg import detect_fvg_zones


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _df(opens, highs, lows, closes) -> pd.DataFrame:
    """Build OHLCV DataFrame from explicit price lists."""
    n = len(closes)
    return pd.DataFrame({
        "time": [datetime(2024, 1, 1) + timedelta(hours=i) for i in range(n)],
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "tick_volume": [100] * n,
    })


# ---------------------------------------------------------------------------
# Bullish FVG detection (FR-005)
# ---------------------------------------------------------------------------

def test_bullish_fvg_detected():
    """3-candle sequence where candle[N-2].high < candle[N].low → bullish FVG (FR-005)."""
    # candle[0].high=1905 (N-2), candle[2].low=1907 (N) → gap: bottom=1905, top=1907
    opens  = [1900, 1904, 1912]
    highs  = [1905, 1915, 1920]
    lows   = [1898, 1903, 1907]
    closes = [1902, 1912, 1915]

    zones = detect_fvg_zones(_df(opens, highs, lows, closes))

    assert len(zones) == 1
    z = zones[0]
    assert z.direction == Direction.LONG
    assert z.bottom == 1905.0
    assert z.top == 1907.0
    assert z.midpoint == pytest.approx((1905.0 + 1907.0) / 2)
    assert z.status == FVGStatus.UNFILLED
    assert z.candle_index == 2


def test_bullish_fvg_top_bottom_boundaries():
    """Bullish FVG: top = candle[N].low, bottom = candle[N-2].high (data-model.md §8)."""
    opens  = [1900, 1905, 1912]
    highs  = [1904, 1916, 1922]
    lows   = [1897, 1904, 1910]
    closes = [1903, 1913, 1918]
    # candle[0].high=1904, candle[2].low=1910 → bottom=1904, top=1910

    zones = detect_fvg_zones(_df(opens, highs, lows, closes))

    assert len(zones) == 1
    assert zones[0].bottom == 1904.0
    assert zones[0].top == 1910.0


# ---------------------------------------------------------------------------
# Bearish FVG detection (FR-006)
# ---------------------------------------------------------------------------

def test_bearish_fvg_detected():
    """3-candle sequence where candle[N-2].low > candle[N].high → bearish FVG (FR-006)."""
    # candle[0].low=1905 (N-2), candle[2].high=1903 (N) → gap: bottom=1903, top=1905
    opens  = [1912, 1908, 1900]
    highs  = [1915, 1910, 1903]
    lows   = [1905, 1897, 1895]
    closes = [1910, 1900, 1897]

    zones = detect_fvg_zones(_df(opens, highs, lows, closes))

    assert len(zones) == 1
    z = zones[0]
    assert z.direction == Direction.SHORT
    assert z.top == 1905.0
    assert z.bottom == 1903.0
    assert z.midpoint == pytest.approx((1905.0 + 1903.0) / 2)
    assert z.status == FVGStatus.UNFILLED
    assert z.candle_index == 2


# ---------------------------------------------------------------------------
# Fill detection — CLOSE only, NOT wick (FR-007)
# ---------------------------------------------------------------------------

def test_wick_into_bullish_fvg_does_not_fill():
    """Wick enters FVG zone but CLOSE stays above → zone remains UNFILLED (FR-007)."""
    # Bullish FVG at index 2: bottom=1905, top=1907
    # Candle 3: wick low=1904 enters zone, but close=1916 is above zone top
    opens  = [1900, 1904, 1912, 1914]
    highs  = [1905, 1915, 1920, 1918]
    lows   = [1898, 1903, 1907, 1904]   # wick low=1904 < zone top=1907
    closes = [1902, 1912, 1915, 1916]   # close=1916 above zone — no fill

    zones = detect_fvg_zones(_df(opens, highs, lows, closes))

    assert len(zones) == 1
    assert zones[0].status == FVGStatus.UNFILLED


def test_close_inside_bullish_fvg_fills_zone():
    """Candle CLOSE inside bullish FVG zone → status transitions to FILLED (FR-007)."""
    # Bullish FVG at index 2: bottom=1905, top=1907
    # Candle 3: close=1906 is inside [1905, 1907] → FILLED
    opens  = [1900, 1904, 1912, 1908]
    highs  = [1905, 1915, 1920, 1916]
    lows   = [1898, 1903, 1907, 1904]
    closes = [1902, 1912, 1915, 1906]   # close=1906 inside zone

    zones = detect_fvg_zones(_df(opens, highs, lows, closes))

    assert len(zones) == 1
    assert zones[0].status == FVGStatus.FILLED


def test_close_inside_bearish_fvg_fills_zone():
    """Candle CLOSE inside bearish FVG zone → status FILLED."""
    # Bearish FVG at index 2: top=1905, bottom=1903
    # Candle 3: close=1904 is inside [1903, 1905] → FILLED
    opens  = [1912, 1908, 1900, 1902]
    highs  = [1915, 1910, 1903, 1907]
    lows   = [1905, 1897, 1895, 1900]
    closes = [1910, 1900, 1897, 1904]   # close=1904 inside zone

    zones = detect_fvg_zones(_df(opens, highs, lows, closes))

    assert len(zones) == 1
    assert zones[0].status == FVGStatus.FILLED


def test_wick_into_bearish_fvg_does_not_fill():
    """Wick enters bearish FVG but CLOSE stays below zone → UNFILLED."""
    # Bearish FVG at index 2: top=1905, bottom=1903
    # Candle 3: wick high=1904 enters zone, but close=1892 is below zone bottom
    opens  = [1912, 1908, 1900, 1895]
    highs  = [1915, 1910, 1903, 1904]   # wick=1904 enters zone (1903–1905)
    lows   = [1905, 1897, 1895, 1890]
    closes = [1910, 1900, 1897, 1892]   # close=1892 below zone bottom=1903

    zones = detect_fvg_zones(_df(opens, highs, lows, closes))

    assert len(zones) == 1
    assert zones[0].status == FVGStatus.UNFILLED


# ---------------------------------------------------------------------------
# Multiple stacked FVGs
# ---------------------------------------------------------------------------

def test_multiple_stacked_fvgs_detected():
    """Two separate 3-candle FVG patterns → two zones ordered newest-first."""
    # FVG 1 at index 2: candle[0].high=1905 < candle[2].low=1907
    # FVG 2 at index 5: candle[3].high=1915 < candle[5].low=1918
    opens  = [1900, 1904, 1912, 1913, 1917, 1922]
    highs  = [1905, 1915, 1920, 1915, 1927, 1930]
    lows   = [1898, 1903, 1907, 1910, 1916, 1918]
    closes = [1902, 1912, 1915, 1913, 1924, 1926]

    zones = detect_fvg_zones(_df(opens, highs, lows, closes))

    assert len(zones) == 2
    assert zones[0].candle_index == 5   # newest-first
    assert zones[1].candle_index == 2


# ---------------------------------------------------------------------------
# Direction filter (FR-008)
# ---------------------------------------------------------------------------

def test_direction_filter_long_returns_only_bullish():
    """direction_filter=Direction.LONG → only LONG FVG zones returned."""
    # Contains both bullish (index 2) and bearish (index 5) FVGs
    opens  = [1900, 1904, 1912, 1925, 1920, 1915]
    highs  = [1905, 1915, 1920, 1928, 1922, 1918]
    lows   = [1898, 1903, 1907, 1920, 1912, 1910]
    closes = [1902, 1912, 1915, 1923, 1914, 1912]

    zones = detect_fvg_zones(_df(opens, highs, lows, closes), direction_filter=Direction.LONG)

    assert len(zones) >= 1
    assert all(z.direction == Direction.LONG for z in zones)


def test_direction_filter_short_returns_only_bearish():
    """direction_filter=Direction.SHORT → only SHORT FVG zones returned."""
    opens  = [1900, 1904, 1912, 1925, 1920, 1915]
    highs  = [1905, 1915, 1920, 1928, 1922, 1918]
    lows   = [1898, 1903, 1907, 1920, 1912, 1910]
    closes = [1902, 1912, 1915, 1923, 1914, 1912]

    zones = detect_fvg_zones(_df(opens, highs, lows, closes), direction_filter=Direction.SHORT)

    assert len(zones) >= 1
    assert all(z.direction == Direction.SHORT for z in zones)


def test_no_filter_returns_all_directions():
    """No direction_filter → both LONG and SHORT zones returned."""
    opens  = [1900, 1904, 1912, 1925, 1920, 1915]
    highs  = [1905, 1915, 1920, 1928, 1922, 1918]
    lows   = [1898, 1903, 1907, 1920, 1912, 1910]
    closes = [1902, 1912, 1915, 1923, 1914, 1912]

    zones = detect_fvg_zones(_df(opens, highs, lows, closes))

    directions = {z.direction for z in zones}
    assert Direction.LONG in directions
    assert Direction.SHORT in directions


# ---------------------------------------------------------------------------
# Empty result when no gap
# ---------------------------------------------------------------------------

def test_no_fvg_when_candles_overlap():
    """Overlapping candle ranges → no imbalance gap → empty list returned."""
    # candle[0].high=1903, candle[2].low=1900 → 1903 > 1900, not a bullish FVG
    # candle[0].low=1898, candle[2].high=1905 → 1898 < 1905, not a bearish FVG
    opens  = [1900, 1901, 1902]
    highs  = [1903, 1904, 1905]
    lows   = [1898, 1899, 1900]
    closes = [1901, 1902, 1903]

    zones = detect_fvg_zones(_df(opens, highs, lows, closes))

    assert zones == []


def test_no_fvg_fewer_than_3_candles():
    """DataFrame with fewer than 3 candles → empty list (no 3-candle window possible)."""
    opens  = [1900, 1901]
    highs  = [1905, 1910]
    lows   = [1895, 1900]
    closes = [1902, 1908]

    zones = detect_fvg_zones(_df(opens, highs, lows, closes))

    assert zones == []


def test_empty_dataframe_returns_empty():
    """Empty DataFrame → empty list."""
    df = pd.DataFrame(columns=["time", "open", "high", "low", "close", "tick_volume"])

    zones = detect_fvg_zones(df)

    assert zones == []


# ---------------------------------------------------------------------------
# Result ordering and return-type contract
# ---------------------------------------------------------------------------

def test_zones_returned_newest_first():
    """Results ordered newest-first by candle_index across all detected zones."""
    opens  = [1900, 1904, 1912, 1913, 1917, 1922]
    highs  = [1905, 1915, 1920, 1915, 1927, 1930]
    lows   = [1898, 1903, 1907, 1910, 1916, 1918]
    closes = [1902, 1912, 1915, 1913, 1924, 1926]

    zones = detect_fvg_zones(_df(opens, highs, lows, closes))

    for i in range(len(zones) - 1):
        assert zones[i].candle_index >= zones[i + 1].candle_index


def test_fvg_zone_field_types():
    """FVGZone fields have correct types: float, Direction, FVGStatus, int."""
    opens  = [1900, 1904, 1912]
    highs  = [1905, 1915, 1920]
    lows   = [1898, 1903, 1907]
    closes = [1902, 1912, 1915]

    zones = detect_fvg_zones(_df(opens, highs, lows, closes))

    assert len(zones) == 1
    z = zones[0]
    assert isinstance(z.top, float)
    assert isinstance(z.bottom, float)
    assert isinstance(z.midpoint, float)
    assert isinstance(z.direction, Direction)
    assert isinstance(z.status, FVGStatus)
    assert isinstance(z.candle_index, int)
