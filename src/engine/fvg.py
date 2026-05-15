"""Fair Value Gap (FVG) imbalance zone detection.

FR-005: Bullish FVG — 3-candle pattern where candle[N-2].high < candle[N].low.
        The middle candle (N-1) is the impulse; the gap above candle N-2 is the imbalance.
FR-006: Bearish FVG — 3-candle pattern where candle[N-2].low > candle[N].high.
        The middle candle moved down so fast it left a gap below candle N-2.
FR-007: Fill detection uses candle CLOSE only — wick entries do NOT fill the zone.
        Wick touches merely test the zone; institutional acceptance requires a candle close
        inside the gap. This prevents premature invalidation from spike candles (D-003).
FR-008: Return all zones ordered newest-first. Honour direction_filter.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.engine.models import Direction, FVGStatus, FVGZone


def detect_fvg_zones(
    df: pd.DataFrame,
    direction_filter: Direction | None = None,
) -> list[FVGZone]:
    """Scan all 3-candle windows in df for Fair Value Gap imbalances.

    3-candle gap rule:
      Bullish FVG: candle[N-2].high < candle[N].low
                   top    = candle[N].low
                   bottom = candle[N-2].high
      Bearish FVG: candle[N-2].low > candle[N].high
                   top    = candle[N-2].low
                   bottom = candle[N].high

    Fill rule: UNFILLED → FILLED when any subsequent candle CLOSE lies inside
    [zone.bottom, zone.top]. Wick entries are intentionally ignored (FR-007).

    Args:
        df:               OHLCV DataFrame, ascending by time. Requires columns:
                          open, high, low, close.
        direction_filter: When set, return only zones matching this direction.
                          None returns all zones regardless of direction.

    Returns:
        List of FVGZone ordered newest-first (descending candle_index).
    """
    if len(df) < 3:
        return []

    # Pre-extract as numpy arrays — avoids repeated pandas row-access overhead (SC-005)
    highs  = df["high"].to_numpy(dtype=float)
    lows   = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    n      = len(df)

    zones: list[FVGZone] = []

    for i in range(2, n):
        h_prev2 = highs[i - 2]
        l_prev2 = lows[i - 2]
        l_curr  = lows[i]
        h_curr  = highs[i]

        # Bullish FVG: gap above candle N-2; price skipped over the range between
        # candle[N-2].high and candle[N].low without any overlap (FR-005)
        if h_prev2 < l_curr:
            top    = l_curr
            bottom = h_prev2
            zones.append(FVGZone(
                top=top,
                bottom=bottom,
                midpoint=(top + bottom) / 2,
                direction=Direction.LONG,
                status=FVGStatus.UNFILLED,
                candle_index=i,
            ))

        # Bearish FVG: gap below candle N-2; downward impulse left an unfilled
        # imbalance between candle[N-2].low and candle[N].high (FR-006)
        elif l_prev2 > h_curr:
            top    = l_prev2
            bottom = h_curr
            zones.append(FVGZone(
                top=top,
                bottom=bottom,
                midpoint=(top + bottom) / 2,
                direction=Direction.SHORT,
                status=FVGStatus.UNFILLED,
                candle_index=i,
            ))

    # Fill check: vectorized numpy scan — CLOSE only, never wicks (FR-007)
    for zone in zones:
        subsequent = closes[zone.candle_index + 1:]
        if len(subsequent) and np.any((subsequent >= zone.bottom) & (subsequent <= zone.top)):
            zone.status = FVGStatus.FILLED

    # Apply direction filter before returning (FR-008)
    if direction_filter is not None:
        zones = [z for z in zones if z.direction == direction_filter]

    # Newest-first so the scorer can pick the most recent active zone
    return sorted(zones, key=lambda z: z.candle_index, reverse=True)
