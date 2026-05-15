"""Fractal swing point detection for the SMC Signal Detection Engine.

FR-001: A pivot is confirmed only when fractal_n candles on EACH side satisfy strict
inequality — strictly lower highs (swing high) or strictly higher lows (swing low).
Unconfirmed pivots (including the last fractal_n rows) are never returned.
"""

from __future__ import annotations

import pandas as pd

from src.engine.models import SwingPoint


def detect_swing_points(
    df: pd.DataFrame,
    fractal_n: int = 2,
    lookback: int = 20,
) -> list[SwingPoint]:
    """Identify confirmed fractal swing highs and lows.

    Fractal rule (FR-001):
      - Swing HIGH at index i: df['high'][i] is strictly greater than the highs of
        the fractal_n candles immediately before and after it.
      - Swing LOW at index i: df['low'][i] is strictly less than the lows of the
        fractal_n candles on each side.

    The last fractal_n rows are always excluded — there are not enough right-side
    candles to confirm a pivot there.

    Args:
        df:        OHLCV DataFrame, ascending by time.
        fractal_n: Number of confirmation candles required on each side (default 2).
        lookback:  Maximum number of candles to scan from the end of df (default 20).

    Returns:
        List of confirmed SwingPoint objects, in candle_index order.
        Returns an empty list when df is too short or no pivots are found.
    """
    if df.empty or len(df) < 2 * fractal_n + 1:
        return []

    n = len(df)
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()

    # Scan only within the lookback window, respecting fractal confirmation bounds
    scan_start = max(fractal_n, n - lookback)
    scan_end = n - fractal_n  # last fractal_n rows are always excluded (unconfirmed)

    results: list[SwingPoint] = []

    for i in range(scan_start, scan_end):
        pivot_high = highs[i]
        pivot_low = lows[i]

        # Left-side and right-side windows for fractal confirmation
        left_slice = slice(i - fractal_n, i)
        right_slice = slice(i + 1, i + fractal_n + 1)

        # Swing HIGH: all neighbouring highs must be STRICTLY lower (FR-001)
        if (highs[left_slice] < pivot_high).all() and (highs[right_slice] < pivot_high).all():
            results.append(SwingPoint(
                price=float(pivot_high),
                candle_index=i,
                type="HIGH",
                confirmed=True,
                fractal_n=fractal_n,
            ))

        # Swing LOW: all neighbouring lows must be STRICTLY higher (FR-001)
        if (lows[left_slice] > pivot_low).all() and (lows[right_slice] > pivot_low).all():
            results.append(SwingPoint(
                price=float(pivot_low),
                candle_index=i,
                type="LOW",
                confirmed=True,
                fractal_n=fractal_n,
            ))

    return results
