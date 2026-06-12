"""ATR computation from OHLCV bars — True Range and Average True Range.

FR-001: TR = max(H-L, |H-PrevClose|, |L-PrevClose|)
FR-002: ATR = simple arithmetic mean of last `period` TR values
FR-012: invalid bars (high < low, close <= 0) are rejected with WARNING log
"""
from __future__ import annotations

from typing import Optional

from loguru import logger

from src.analysis.models import OHLCVBar


def validate_ohlcv_bars(bars: list[OHLCVBar]) -> list[OHLCVBar]:
    """Return only valid bars; log WARNING per rejected bar (FR-012).

    A bar is invalid if high < low or close <= 0.
    Returns empty list if all bars are invalid. Never raises.
    """
    valid: list[OHLCVBar] = []
    for bar in bars:
        if bar.high < bar.low:
            logger.warning(
                "Invalid OHLCV bar rejected (high={} < low={}) at {}",
                bar.high, bar.low, bar.timestamp,
            )
        elif bar.close <= 0:
            logger.warning(
                "Invalid OHLCV bar rejected (close={} <= 0) at {}",
                bar.close, bar.timestamp,
            )
        else:
            valid.append(bar)
    return valid


def compute_true_range(bars: list[OHLCVBar]) -> list[float]:
    """Return True Range for each bar except the first (requires a prev_close).

    TR = max(high − low, |high − prev_close|, |low − prev_close|)
    Returns list of length len(bars) − 1.
    Raises ValueError if fewer than 2 bars are provided.
    """
    if len(bars) < 2:
        raise ValueError(
            f"compute_true_range requires at least 2 bars, got {len(bars)}"
        )
    tr_values: list[float] = []
    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        high = bars[i].high
        low  = bars[i].low
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low  - prev_close),
        )
        tr_values.append(tr)
    return tr_values


def compute_atr(bars: list[OHLCVBar], period: int = 14) -> Optional[float]:
    """Return simple-average ATR over the last `period` True Range values (FR-002).

    Expects bars that have already been validated (caller's responsibility).
    Returns None if len(bars) < period + 1 (D-007: insufficient data — never returns 0.0).
    """
    if len(bars) < period + 1:
        return None
    tr_values = compute_true_range(bars)
    recent_tr = tr_values[-period:]
    return sum(recent_tr) / len(recent_tr)
