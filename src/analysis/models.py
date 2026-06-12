"""Data models for the ATR Calibration Module — spec006."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class Timeframe(Enum):
    """Trading timeframe. Value = MT5 timeframe constant for direct broker passthrough."""
    M5 = 5
    H1 = 16385
    H4 = 16388
    D1 = 16408


@dataclass(frozen=True)
class OHLCVBar:
    """One OHLCV bar received from the broker data feed (spec001)."""
    open:      float
    high:      float
    low:       float
    close:     float
    volume:    float
    timestamp: datetime


class VolatilityRegime(Enum):
    """Volatility classification derived from ATR ratio (current / reference).

    Thresholds configured in filters.volatility config (spec004).
    """
    LOW     = "LOW"
    NORMAL  = "NORMAL"
    EXTREME = "EXTREME"


@dataclass(frozen=True)
class AdaptiveMultipliers:
    """SL and TP multipliers selected for a given VolatilityRegime.

    Supplied by get_adaptive_multipliers() to lot_calculator (spec003).
    """
    sl_multiplier: float
    tp_multiplier: float
    regime:        VolatilityRegime


@dataclass
class ATRReading:
    """One computed ATR result for a given timeframe."""
    timeframe:     Timeframe
    current_atr:   Optional[float]   # None if insufficient data (< period bars)
    reference_atr: Optional[float]   # None if insufficient ATR history (< ref_period values)
    ratio:         Optional[float]   # current_atr / reference_atr; None if either is None
    bar_count:     int               # number of valid bars used for this computation
    timestamp:     datetime


@dataclass
class ATRCache:
    """Per-timeframe ATR cache entry. Invalidated (is_fresh=False) on bar-close signal."""
    reading:        ATRReading
    is_fresh:       bool
    last_refreshed: datetime
