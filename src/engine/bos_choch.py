"""BOS (Break of Structure) and CHoCH (Change of Character) detection.

FR-002: BOS detected when candle CLOSE breaks beyond the most recent confirmed swing high
        (bullish BOS) or swing low (bearish BOS) — trend continuation.
FR-003: CHoCH detected when price breaks against the established trend direction —
        reversal signal.
FR-004: Candle-close rule — df['close'] is used exclusively. Wick moves (high/low)
        NEVER trigger a BOS or CHoCH. This prevents false signals from spike candles.
D-006:  Established trend is derived from the direction of most recent swing structure
        (higher highs + higher lows = bullish; lower highs + lower lows = bearish).
"""

from __future__ import annotations

import pandas as pd

from src.engine.models import SignalType, SwingPoint


def detect_structure_break(
    df: pd.DataFrame,
    swing_points: list[SwingPoint],
) -> tuple[SignalType, float | None]:
    """Detect the most recent BOS or CHoCH from confirmed swing points.

    Uses candle CLOSE only — wick moves never trigger a structural event (FR-004).
    CHoCH requires an established trend inferred from the swing structure (D-006):
      - Bullish trend (HH + HL) + close below swing low  → CHoCH_BEARISH
      - Bearish trend (LH + LL) + close above swing high → CHoCH_BULLISH
    Without an established trend, any structural break is classified as BOS.

    Args:
        df:           OHLCV DataFrame, ascending by time.
        swing_points: Confirmed swing points from detect_swing_points().

    Returns:
        (SignalType, broken_level_price) on a confirmed break.
        (SignalType.NONE, None) for ranging market or no break.
    """
    if not swing_points or df.empty:
        return (SignalType.NONE, None)

    highs = sorted([s for s in swing_points if s.type == "HIGH"], key=lambda s: s.candle_index)
    lows  = sorted([s for s in swing_points if s.type == "LOW"],  key=lambda s: s.candle_index)

    # Close-only rule: never use df['high'] or df['low'] for structural detection (FR-004)
    last_close = float(df["close"].iloc[-1])

    broke_high = bool(highs and last_close > highs[-1].price)
    broke_low  = bool(lows  and last_close < lows[-1].price)

    if not broke_high and not broke_low:
        return (SignalType.NONE, None)

    established_trend = _infer_established_trend(highs, lows)

    if broke_high:
        # Breaking above swing HIGH in a bearish trend = reversal (CHoCH); otherwise continuation (BOS)
        if established_trend == "BEARISH":
            return (SignalType.CHOCH_BULLISH, highs[-1].price)
        return (SignalType.BOS_BULLISH, highs[-1].price)

    # broke_low
    # Breaking below swing LOW in a bullish trend = reversal (CHoCH); otherwise continuation (BOS)
    if established_trend == "BULLISH":
        return (SignalType.CHOCH_BEARISH, lows[-1].price)
    return (SignalType.BOS_BEARISH, lows[-1].price)


def _infer_established_trend(
    highs: list[SwingPoint],
    lows: list[SwingPoint],
) -> str | None:
    """Derive established trend from the swing structure (D-006).

    Classic SMC structure analysis:
      Higher Highs + Higher Lows = bullish trend
      Lower  Highs + Lower  Lows = bearish trend
    Single-series signals (only highs or only lows available) are used as tiebreaker.
    Returns 'BULLISH', 'BEARISH', or None when structure is ambiguous.
    """
    hh = len(highs) >= 2 and highs[-1].price > highs[-2].price   # higher high
    lh = len(highs) >= 2 and highs[-1].price < highs[-2].price   # lower high
    hl = len(lows)  >= 2 and lows[-1].price  > lows[-2].price    # higher low
    ll = len(lows)  >= 2 and lows[-1].price  < lows[-2].price    # lower low

    # Full confluence: both HH+HL or LH+LL
    if hh and hl:
        return "BULLISH"
    if lh and ll:
        return "BEARISH"

    # Single-series tiebreakers
    if hh or hl:
        return "BULLISH"
    if lh or ll:
        return "BEARISH"

    return None
