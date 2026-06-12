"""Rolling reference ATR computation — baseline for volatility ratio (FR-004).

reference_atr = arithmetic mean of the last N ATR values (default N=20).
Same input always produces same output (SC-007 determinism).
"""
from __future__ import annotations

from typing import Optional


def compute_reference_atr(atr_history: list[float], period: int = 20) -> Optional[float]:
    """Return the rolling average of the last `period` ATR values (FR-004).

    Args:
        atr_history: ATR values in chronological order (oldest first, newest last).
        period:      Number of recent ATR values to average (default: 20).

    Returns:
        Float mean if len(atr_history) >= period, else None (insufficient history).
        Same input always returns same output (deterministic — no side effects).
    """
    if len(atr_history) < period:
        return None
    window = atr_history[-period:]
    return sum(window) / len(window)
