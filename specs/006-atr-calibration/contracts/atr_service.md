# API Contract: ATR Calibration Module

**Feature**: 006-atr-calibration  
**Date**: 2026-05-22  
**Module**: `src/analysis/`

---

## `src/analysis/models.py`

```python
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

class Timeframe(Enum):
    M5  = 5
    H1  = 16385
    H4  = 16388
    D1  = 16408

class VolatilityRegime(Enum):
    LOW     = "LOW"
    NORMAL  = "NORMAL"
    EXTREME = "EXTREME"

@dataclass(frozen=True)
class OHLCVBar:
    open:      float
    high:      float
    low:       float
    close:     float
    volume:    float
    timestamp: datetime

@dataclass(frozen=True)
class AdaptiveMultipliers:
    sl_multiplier: float
    tp_multiplier: float
    regime:        VolatilityRegime

@dataclass
class ATRReading:
    timeframe:     Timeframe
    current_atr:   Optional[float]   # None if insufficient data
    reference_atr: Optional[float]   # None if insufficient history
    ratio:         Optional[float]   # current_atr / reference_atr; None if either is None
    bar_count:     int
    timestamp:     datetime

@dataclass
class ATRCache:
    reading:        ATRReading
    is_fresh:       bool
    last_refreshed: datetime
```

---

## `src/analysis/atr_calculator.py`

### `validate_ohlcv_bars`

```python
def validate_ohlcv_bars(bars: list[OHLCVBar]) -> list[OHLCVBar]:
    """Return only valid bars; log WARNING for each rejected bar.

    Rejects bars where high < low or close <= 0 (FR-012).
    Never raises — returns empty list if all bars invalid.
    """
```

### `compute_true_range`

```python
def compute_true_range(bars: list[OHLCVBar]) -> list[float]:
    """Return True Range for each bar (except the first, which has no prev_close).

    TR = max(high - low, |high - prev_close|, |low - prev_close|)
    Returns list of length len(bars) - 1.
    Raises ValueError if bars is empty or has < 2 elements.
    """
```

### `compute_atr`

```python
def compute_atr(bars: list[OHLCVBar], period: int = 14) -> Optional[float]:
    """Return simple average ATR over the last `period` True Range values (FR-001, FR-002).

    Returns None if len(valid_bars) < period + 1 (insufficient data, D-007).
    Never raises for normal inputs.
    """
```

---

## `src/analysis/reference_atr.py`

### `compute_reference_atr`

```python
def compute_reference_atr(atr_history: list[float], period: int = 20) -> Optional[float]:
    """Return rolling average of the last `period` ATR values (FR-004).

    Returns None if len(atr_history) < period.
    atr_history: ordered oldest-first, newest last.
    Same input always produces same output (SC-007 determinism).
    """
```

---

## `src/analysis/adaptive_multipliers.py`

### `get_adaptive_multipliers`

```python
def get_adaptive_multipliers(
    regime: VolatilityRegime,
    config: dict,
) -> AdaptiveMultipliers:
    """Return SL and TP multipliers for the given volatility regime (FR-007, FR-008).

    Reads from config['analysis']['atr']['adaptive_multipliers'].
    Raises KeyError if config section is missing.
    """
```

---

## `src/analysis/atr_service.py`

### `ATRService`

```python
class ATRService:
    def __init__(self, config: dict) -> None:
        """Initialise with empty cache for all four timeframes.

        config must contain 'analysis.atr' section (FR-013).
        """

    def refresh(self, timeframe: Timeframe, bars: list[OHLCVBar]) -> ATRReading:
        """Compute fresh ATR from provided OHLCV bars and update cache (FR-009, FR-010).

        - Validates bars (FR-012); invalid bars skipped and logged.
        - Computes current_atr and reference_atr.
        - Updates cache entry for this timeframe; marks is_fresh = True.
        - If computation fails (e.g., all bars invalid), preserves last cached value,
          marks is_fresh = False, logs WARNING with timeframe + timestamp (FR-011).
        - Returns the new ATRReading (or last valid reading on failure).
        - Never raises.
        """

    def get_atr(self, timeframe: Timeframe) -> Optional[float]:
        """Return cached current_atr for timeframe, or None if cache is empty (D-007).

        Does NOT trigger a refresh — caller must call refresh() on bar close.
        """

    def get_h1_readings(self) -> tuple[Optional[float], Optional[float]]:
        """Return (current_h1_atr, reference_h1_atr) for use by volatility_filter (FR-005).

        Both values are None if H1 cache is empty.
        """

    def get_d1_atr(self) -> Optional[float]:
        """Return cached D1 ATR for use by lot_calculator.calculate_sl_price() (FR-006).

        Returns None if D1 cache is empty.
        """

    def get_adaptive_multipliers(self, regime: VolatilityRegime) -> AdaptiveMultipliers:
        """Return SL/TP multipliers for the given regime (FR-007, FR-008).

        Delegates to adaptive_multipliers.get_adaptive_multipliers().
        """

    def is_ready(self, timeframe: Timeframe) -> bool:
        """Return True if cache for timeframe has a valid (non-None) ATR reading."""

    def mark_stale(self, timeframe: Timeframe) -> None:
        """Mark cache entry as stale (called by orchestrator before bar refresh)."""
```

---

## Error Contract

| Situation | Behaviour |
|-----------|-----------|
| < 14 valid bars for `compute_atr` | Returns `None`; no exception |
| < 20 ATR values for `compute_reference_atr` | Returns `None`; no exception |
| All bars invalid (High < Low) | Logs WARNING per bar; `compute_atr` returns `None` |
| Refresh fails (data source error) | Last valid cached value preserved; WARNING logged; no exception |
| Empty cache + `get_atr()` called | Returns `None`; no exception |
| Missing config key | Raises `KeyError` with descriptive message |

---

## `src/analysis/__init__.py` — Public Exports

```python
from src.analysis.models import (
    Timeframe,
    VolatilityRegime,
    OHLCVBar,
    AdaptiveMultipliers,
    ATRReading,
    ATRCache,
)
from src.analysis.atr_service import ATRService
from src.analysis.atr_calculator import compute_atr, compute_true_range, validate_ohlcv_bars
from src.analysis.reference_atr import compute_reference_atr
from src.analysis.adaptive_multipliers import get_adaptive_multipliers
```
