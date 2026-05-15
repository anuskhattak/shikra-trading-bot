"""Unit tests for Order Block detection.

Write-first (TDD): these tests must FAIL before src/engine/order_block.py exists.
Checkpoint: pytest tests/unit/test_engine_order_block.py — all must pass after T015.
"""

import pandas as pd
import pytest
from datetime import datetime, timedelta

from src.engine.models import Direction, OBStatus, OrderBlock, SignalType
from src.engine.order_block import detect_order_blocks


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
# Bullish OB detection (FR-009)
# ---------------------------------------------------------------------------

def test_bullish_ob_detected():
    """Last bearish candle before bullish BOS → Bullish OB, direction=LONG (FR-009)."""
    # Candle 0: bearish (open=1910 > close=1905) → OB candidate
    # Candle 1: impulse up
    # Candle 2: BOS_BULLISH
    opens  = [1910, 1905, 1920]
    highs  = [1915, 1925, 1930]
    lows   = [1898, 1904, 1919]
    closes = [1905, 1922, 1928]

    obs = detect_order_blocks(_df(opens, highs, lows, closes), SignalType.BOS_BULLISH, bos_candle_index=2)

    assert len(obs) == 1
    ob = obs[0]
    assert ob.direction == Direction.LONG
    assert ob.top == 1910.0
    assert ob.bottom == 1905.0
    assert ob.status == OBStatus.ACTIVE
    assert ob.candle_index == 0


# ---------------------------------------------------------------------------
# Bearish OB detection (FR-010)
# ---------------------------------------------------------------------------

def test_bearish_ob_detected():
    """Last bullish candle before bearish BOS → Bearish OB, direction=SHORT (FR-010)."""
    # Candle 0: bullish (open=1900 < close=1910) → OB candidate
    # Candle 1: impulse down
    # Candle 2: BOS_BEARISH
    opens  = [1900, 1910, 1890]
    highs  = [1915, 1912, 1892]
    lows   = [1898, 1885, 1882]
    closes = [1910, 1888, 1885]

    obs = detect_order_blocks(_df(opens, highs, lows, closes), SignalType.BOS_BEARISH, bos_candle_index=2)

    assert len(obs) == 1
    ob = obs[0]
    assert ob.direction == Direction.SHORT
    assert ob.top == 1910.0
    assert ob.bottom == 1900.0
    assert ob.status == OBStatus.ACTIVE
    assert ob.candle_index == 0


# ---------------------------------------------------------------------------
# Body boundaries — wicks excluded (FR-012)
# ---------------------------------------------------------------------------

def test_ob_body_boundaries_not_wicks():
    """OB top = max(open,close), bottom = min(open,close) — wicks excluded (FR-012)."""
    # Candle 0: bearish, large wicks: open=1910, close=1905, high=1920, low=1895
    # OB must use body only: top=1910, bottom=1905 (NOT high=1920 or low=1895)
    opens  = [1910, 1905, 1920]
    highs  = [1920, 1925, 1930]
    lows   = [1895, 1904, 1919]
    closes = [1905, 1922, 1928]

    obs = detect_order_blocks(_df(opens, highs, lows, closes), SignalType.BOS_BULLISH, bos_candle_index=2)

    assert len(obs) == 1
    ob = obs[0]
    assert ob.top == 1910.0      # max(open=1910, close=1905), NOT high=1920
    assert ob.bottom == 1905.0   # min(open=1910, close=1905), NOT low=1895


def test_bearish_ob_body_boundaries_not_wicks():
    """Bearish OB body: top=max(open,close), bottom=min(open,close); wicks excluded."""
    # Candle 0: bullish, large wicks: open=1900, close=1910, high=1920, low=1890
    opens  = [1900, 1910, 1890]
    highs  = [1920, 1912, 1892]
    lows   = [1890, 1885, 1882]
    closes = [1910, 1888, 1885]

    obs = detect_order_blocks(_df(opens, highs, lows, closes), SignalType.BOS_BEARISH, bos_candle_index=2)

    assert len(obs) == 1
    assert obs[0].top == 1910.0      # max(open=1900, close=1910)
    assert obs[0].bottom == 1900.0   # min(open=1900, close=1910)


# ---------------------------------------------------------------------------
# State transitions — ACTIVE → TESTED → INVALIDATED (D-007, FR-011)
# ---------------------------------------------------------------------------

def test_bullish_ob_active_to_tested_on_wick_entry():
    """Wick enters bullish OB zone (candle.low <= ob.top) → status TESTED (D-007)."""
    # OB: top=1910, bottom=1905
    # Candle 3: low=1908 <= ob.top=1910, close=1915 >= ob.bottom → TESTED
    opens  = [1910, 1905, 1920, 1915]
    highs  = [1915, 1925, 1930, 1920]
    lows   = [1898, 1904, 1919, 1908]   # candle 3: wick enters OB zone
    closes = [1905, 1922, 1928, 1915]   # close=1915 above zone → TESTED not INVALIDATED

    obs = detect_order_blocks(_df(opens, highs, lows, closes), SignalType.BOS_BULLISH, bos_candle_index=2)

    assert len(obs) == 1
    assert obs[0].status == OBStatus.TESTED


def test_bullish_ob_tested_to_invalidated_on_close_through():
    """After TESTED, candle close below ob.bottom → INVALIDATED (D-007)."""
    # Candle 3: wick test → TESTED; candle 4: close=1904 < ob.bottom=1905 → INVALIDATED
    opens  = [1910, 1905, 1920, 1915, 1906]
    highs  = [1915, 1925, 1930, 1920, 1910]
    lows   = [1898, 1904, 1919, 1908, 1900]
    closes = [1905, 1922, 1928, 1915, 1904]   # candle 4: close < ob.bottom → INVALIDATED

    obs = detect_order_blocks(_df(opens, highs, lows, closes), SignalType.BOS_BULLISH, bos_candle_index=2)

    assert len(obs) == 1
    assert obs[0].status == OBStatus.INVALIDATED


def test_bullish_ob_fast_move_active_to_invalidated():
    """Wick enters OB AND close through body in same candle → INVALIDATED directly (D-007)."""
    # Candle 3: low=1903 enters zone (1903 <= ob.top=1910), close=1903 < ob.bottom=1905
    # Fast move: no separate TESTED phase
    opens  = [1910, 1905, 1920, 1915]
    highs  = [1915, 1925, 1930, 1920]
    lows   = [1898, 1904, 1919, 1903]   # low enters zone
    closes = [1905, 1922, 1928, 1903]   # close < ob.bottom → fast INVALIDATED

    obs = detect_order_blocks(_df(opens, highs, lows, closes), SignalType.BOS_BULLISH, bos_candle_index=2)

    assert len(obs) == 1
    assert obs[0].status == OBStatus.INVALIDATED


def test_bullish_ob_stays_active_when_price_moves_away():
    """Price moves away from OB without touching it → status stays ACTIVE."""
    # OB: top=1910, bottom=1905; candle 3 low=1920 > ob.top → no touch → ACTIVE
    opens  = [1910, 1905, 1920, 1922]
    highs  = [1915, 1925, 1930, 1935]
    lows   = [1898, 1904, 1919, 1920]   # candle 3 low=1920 > ob.top=1910
    closes = [1905, 1922, 1928, 1930]

    obs = detect_order_blocks(_df(opens, highs, lows, closes), SignalType.BOS_BULLISH, bos_candle_index=2)

    assert len(obs) == 1
    assert obs[0].status == OBStatus.ACTIVE


# ---------------------------------------------------------------------------
# Bearish OB state transitions
# ---------------------------------------------------------------------------

def test_bearish_ob_active_to_tested_on_wick_entry():
    """Wick enters bearish OB from below (candle.high >= ob.bottom) → TESTED."""
    # OB: top=1910, bottom=1900
    # Candle 3: high=1901 >= ob.bottom=1900, close=1895 < ob.top=1910 → TESTED
    opens  = [1900, 1910, 1890, 1892]
    highs  = [1915, 1912, 1892, 1901]   # candle 3: wick enters OB zone from below
    lows   = [1898, 1885, 1882, 1890]
    closes = [1910, 1888, 1885, 1895]   # close < ob.top → TESTED not INVALIDATED

    obs = detect_order_blocks(_df(opens, highs, lows, closes), SignalType.BOS_BEARISH, bos_candle_index=2)

    assert len(obs) == 1
    assert obs[0].status == OBStatus.TESTED


def test_bearish_ob_tested_to_invalidated_on_close_through():
    """After TESTED, candle close above ob.top → INVALIDATED."""
    # Candle 3: wick test → TESTED; candle 4: close=1912 > ob.top=1910 → INVALIDATED
    opens  = [1900, 1910, 1890, 1892, 1900]
    highs  = [1915, 1912, 1892, 1901, 1915]
    lows   = [1898, 1885, 1882, 1890, 1898]
    closes = [1910, 1888, 1885, 1895, 1912]   # candle 4: close > ob.top → INVALIDATED

    obs = detect_order_blocks(_df(opens, highs, lows, closes), SignalType.BOS_BEARISH, bos_candle_index=2)

    assert len(obs) == 1
    assert obs[0].status == OBStatus.INVALIDATED


def test_bearish_ob_fast_move_active_to_invalidated():
    """Wick enters bearish OB AND close through top in same candle → INVALIDATED directly."""
    # Candle 3: high=1905 enters zone (1905 >= ob.bottom=1900), close=1915 > ob.top=1910
    opens  = [1900, 1910, 1890, 1892]
    highs  = [1915, 1912, 1892, 1905]   # candle 3: high enters zone
    lows   = [1898, 1885, 1882, 1890]
    closes = [1910, 1888, 1885, 1915]   # close > ob.top → fast INVALIDATED

    obs = detect_order_blocks(_df(opens, highs, lows, closes), SignalType.BOS_BEARISH, bos_candle_index=2)

    assert len(obs) == 1
    assert obs[0].status == OBStatus.INVALIDATED


# ---------------------------------------------------------------------------
# No OB cases
# ---------------------------------------------------------------------------

def test_no_ob_when_signal_none():
    """SignalType.NONE → empty list (no structure event to anchor OB)."""
    opens  = [1910, 1905, 1920]
    highs  = [1915, 1925, 1930]
    lows   = [1898, 1904, 1919]
    closes = [1905, 1922, 1928]

    obs = detect_order_blocks(_df(opens, highs, lows, closes), SignalType.NONE, bos_candle_index=2)

    assert obs == []


def test_no_ob_when_no_opposing_candle_before_bos():
    """All candles before BOS are same direction as BOS → no OB candidate → empty list."""
    # All candles 0 and 1 are bullish (close > open) → no bearish OB for BOS_BULLISH
    opens  = [1900, 1905, 1920]
    highs  = [1910, 1915, 1930]
    lows   = [1898, 1903, 1919]
    closes = [1908, 1913, 1928]   # close > open for both → bullish, not bearish OB

    obs = detect_order_blocks(_df(opens, highs, lows, closes), SignalType.BOS_BULLISH, bos_candle_index=2)

    assert obs == []


def test_no_ob_when_bos_candle_index_zero():
    """bos_candle_index=0 → no candles before BOS to search → empty list."""
    opens  = [1910]
    highs  = [1915]
    lows   = [1898]
    closes = [1905]

    obs = detect_order_blocks(_df(opens, highs, lows, closes), SignalType.BOS_BULLISH, bos_candle_index=0)

    assert obs == []


# ---------------------------------------------------------------------------
# Last opposing candle selected (not first)
# ---------------------------------------------------------------------------

def test_last_opposing_candle_selected_not_first():
    """Multiple bearish candles before BOS → most recent one is the OB (FR-009)."""
    # Candle 0: bearish (open=1915, close=1910)
    # Candle 1: bearish (open=1912, close=1905) ← this is the last → OB
    # Candle 2: BOS
    opens  = [1915, 1912, 1920]
    highs  = [1918, 1915, 1930]
    lows   = [1905, 1900, 1919]
    closes = [1910, 1905, 1928]

    obs = detect_order_blocks(_df(opens, highs, lows, closes), SignalType.BOS_BULLISH, bos_candle_index=2)

    assert len(obs) == 1
    assert obs[0].candle_index == 1          # most recent bearish candle
    assert obs[0].top == 1912.0              # max(open=1912, close=1905)
    assert obs[0].bottom == 1905.0           # min(open=1912, close=1905)


# ---------------------------------------------------------------------------
# CHoCH also creates OB (same logic as BOS)
# ---------------------------------------------------------------------------

def test_choch_bullish_creates_long_ob():
    """CHoCH_BULLISH treated identically to BOS_BULLISH — last bearish candle → OB."""
    opens  = [1910, 1905, 1920]
    highs  = [1915, 1925, 1930]
    lows   = [1898, 1904, 1919]
    closes = [1905, 1922, 1928]

    obs = detect_order_blocks(_df(opens, highs, lows, closes), SignalType.CHOCH_BULLISH, bos_candle_index=2)

    assert len(obs) == 1
    assert obs[0].direction == Direction.LONG


def test_choch_bearish_creates_short_ob():
    """CHoCH_BEARISH treated identically to BOS_BEARISH — last bullish candle → OB."""
    opens  = [1900, 1910, 1890]
    highs  = [1915, 1912, 1892]
    lows   = [1898, 1885, 1882]
    closes = [1910, 1888, 1885]

    obs = detect_order_blocks(_df(opens, highs, lows, closes), SignalType.CHOCH_BEARISH, bos_candle_index=2)

    assert len(obs) == 1
    assert obs[0].direction == Direction.SHORT


# ---------------------------------------------------------------------------
# Return type contract
# ---------------------------------------------------------------------------

def test_return_type_and_field_types():
    """Return value is list[OrderBlock] with correct field types."""
    opens  = [1910, 1905, 1920]
    highs  = [1915, 1925, 1930]
    lows   = [1898, 1904, 1919]
    closes = [1905, 1922, 1928]

    obs = detect_order_blocks(_df(opens, highs, lows, closes), SignalType.BOS_BULLISH, bos_candle_index=2)

    assert isinstance(obs, list)
    assert len(obs) == 1
    ob = obs[0]
    assert isinstance(ob.top, float)
    assert isinstance(ob.bottom, float)
    assert isinstance(ob.direction, Direction)
    assert isinstance(ob.status, OBStatus)
    assert isinstance(ob.candle_index, int)
