"""Order Block detection — last opposing candle before a BOS/CHoCH event.

FR-009: Bullish OB = last bearish candle (close < open) before a bullish BOS/CHoCH.
        This is the final institutional sell footprint before smart money reverses bullish.
FR-010: Bearish OB = last bullish candle (close > open) before a bearish BOS/CHoCH.
        This is the final institutional buy footprint before smart money reverses bearish.
FR-011: OB invalidated by candle-close rule — a candle closing THROUGH the body destroys
        the zone. A wick entry alone does NOT invalidate (D-007).
FR-012: OB boundaries use the candle BODY only — max/min of open and close.
        Wicks are excluded because institutional orders fill at the body level;
        wick extremes reflect transient rejection, not the zone where orders rest.
D-007:  TESTED vs INVALIDATED have different semantics and therefore different trigger rules:
        TESTED means price visited the zone (wick) — zone is still structurally intact.
        INVALIDATED means price closed through the body — zone is structurally destroyed.
"""

from __future__ import annotations

import pandas as pd

from src.engine.models import Direction, OBStatus, OrderBlock, SignalType


_BULLISH_TYPES = {SignalType.BOS_BULLISH, SignalType.CHOCH_BULLISH}
_BEARISH_TYPES = {SignalType.BOS_BEARISH, SignalType.CHOCH_BEARISH}


def detect_order_blocks(
    df: pd.DataFrame,
    bos_type: SignalType,
    bos_candle_index: int,
) -> list[OrderBlock]:
    """Identify the last opposing candle before a BOS/CHoCH as an Order Block.

    OB origin rule (FR-009/FR-010): Scan backwards from the BOS candle to find
    the most recent candle opposing the BOS direction:
      Bullish BOS → last bearish candle (close < open)
      Bearish BOS → last bullish candle (close > open)

    Body-only boundaries (FR-012): top = max(open, close), bottom = min(open, close).
    Wicks are intentionally excluded — the zone of institutional interest is the body,
    not the transient excursions beyond it.

    State machine applied to all candles after the BOS candle (D-007, FR-011):

      Bullish OB:
        ACTIVE → TESTED:      candle.low  <= ob.top    (wick enters from above)
        TESTED → INVALIDATED: candle.close < ob.bottom (close-through below body)
        ACTIVE → INVALIDATED: wick entry AND close-through in same candle (fast move)

      Bearish OB:
        ACTIVE → TESTED:      candle.high >= ob.bottom (wick enters from below)
        TESTED → INVALIDATED: candle.close > ob.top    (close-through above body)
        ACTIVE → INVALIDATED: wick entry AND close-through in same candle (fast move)

    Args:
        df:               OHLCV DataFrame, ascending by time.
        bos_type:         Structural event that defines OB direction context.
        bos_candle_index: Index of the BOS/CHoCH candle in df.

    Returns:
        [OrderBlock] with current status, or [] if no valid OB found.
    """
    if bos_type not in _BULLISH_TYPES | _BEARISH_TYPES:
        return []

    if bos_candle_index <= 0 or bos_candle_index >= len(df):
        return []

    is_bullish = bos_type in _BULLISH_TYPES

    # Scan backwards from BOS candle to find the last opposing candle (FR-009/FR-010).
    # "Last opposing" = most recent candle before BOS whose body direction opposes the BOS.
    ob_candle = None
    ob_candle_index = -1
    for i in range(bos_candle_index - 1, -1, -1):
        c_open  = float(df.iloc[i]["open"])
        c_close = float(df.iloc[i]["close"])
        # Bullish BOS requires a bearish OB candle (close < open) — last sell before the bullish break
        # Bearish BOS requires a bullish OB candle (close > open) — last buy before the bearish break
        if is_bullish and c_close < c_open:
            ob_candle = df.iloc[i]
            ob_candle_index = i
            break
        if not is_bullish and c_close > c_open:
            ob_candle = df.iloc[i]
            ob_candle_index = i
            break

    if ob_candle is None:
        return []

    # Body-only boundaries — open and close only; wicks excluded (FR-012)
    ob_open  = float(ob_candle["open"])
    ob_close = float(ob_candle["close"])
    top    = max(ob_open, ob_close)
    bottom = min(ob_open, ob_close)

    ob = OrderBlock(
        top=top,
        bottom=bottom,
        direction=Direction.LONG if is_bullish else Direction.SHORT,
        status=OBStatus.ACTIVE,
        candle_index=ob_candle_index,
    )

    # Apply state transitions to all candles that appear after the BOS candle (D-007).
    # The BOS candle itself is excluded — OB status tracks post-BOS price action only.
    for j in range(bos_candle_index + 1, len(df)):
        low_   = float(df.iloc[j]["low"])
        high_  = float(df.iloc[j]["high"])
        close_ = float(df.iloc[j]["close"])

        if ob.direction == Direction.LONG:
            # Bullish OB: price should pull back down toward the zone
            if ob.status == OBStatus.ACTIVE and low_ <= ob.top:
                # Wick entered the zone; check if close also punched through the body
                # close < ob.bottom AND low <= ob.top is the fast-move scenario (D-007)
                ob.status = OBStatus.INVALIDATED if close_ < ob.bottom else OBStatus.TESTED

            elif ob.status == OBStatus.TESTED and close_ < ob.bottom:
                # Zone was visited; now a close-through confirms structural destruction (FR-011)
                ob.status = OBStatus.INVALIDATED

        else:
            # Bearish OB: price should pull back up toward the zone
            if ob.status == OBStatus.ACTIVE and high_ >= ob.bottom:
                # Wick entered the zone from below; check for fast close-through above
                ob.status = OBStatus.INVALIDATED if close_ > ob.top else OBStatus.TESTED

            elif ob.status == OBStatus.TESTED and close_ > ob.top:
                # Zone was visited; close-through above destroys the zone (FR-011)
                ob.status = OBStatus.INVALIDATED

        if ob.status == OBStatus.INVALIDATED:
            break   # zone is gone — no need to scan further candles

    return [ob]
