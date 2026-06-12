"""Data models for the SMC Signal Detection Engine.

All enums and dataclasses shared across engine modules live here.
Downstream modules import from this file; never cross-import between detectors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Bias(Enum):
    """Higher-timeframe directional bias — supplied by the caller, never derived."""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    RANGING = "RANGING"


class Direction(Enum):
    """Trade direction of a detected signal."""
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


class SignalType(Enum):
    """Structural market event that triggered the signal."""
    BOS_BULLISH = "BOS_BULLISH"    # Break of Structure upward (trend continuation)
    BOS_BEARISH = "BOS_BEARISH"    # Break of Structure downward (trend continuation)
    CHOCH_BULLISH = "CHOCH_BULLISH"  # Change of Character — reversal bearish→bullish
    CHOCH_BEARISH = "CHOCH_BEARISH"  # Change of Character — reversal bullish→bearish
    NONE = "NONE"


class FVGStatus(Enum):
    """Fill state of a Fair Value Gap zone."""
    UNFILLED = "UNFILLED"   # Gap not yet revisited — active entry zone
    FILLED = "FILLED"       # A subsequent candle CLOSED inside the zone


class OBStatus(Enum):
    """Lifecycle state of an Order Block."""
    ACTIVE = "ACTIVE"           # OB detected; price has not returned
    TESTED = "TESTED"           # A wick entered the zone but no close-through
    INVALIDATED = "INVALIDATED" # A candle closed through the OB body


class SweepType(Enum):
    """Direction of a liquidity sweep (stop-hunt) event."""
    HIGH = "HIGH"   # Wick above equal highs, close back below
    LOW = "LOW"     # Wick below equal lows, close back above


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SwingPoint:
    """A confirmed fractal pivot high or low.

    Confirmed when fractal_n candles on each side satisfy the fractal rule:
    strictly lower highs (swing high) or strictly higher lows (swing low).
    Unconfirmed pivots are never returned by detect_swing_points() (FR-001).
    """
    price: float
    candle_index: int
    type: str       # "HIGH" or "LOW"
    confirmed: bool
    fractal_n: int


@dataclass
class FVGZone:
    """A Fair Value Gap imbalance zone identified from a 3-candle pattern.

    Bullish FVG: candle[N-2].high < candle[N].low  (gap above prior candle)
    Bearish FVG: candle[N-2].low  > candle[N].high (gap below prior candle)

    Fill rule: status transitions UNFILLED → FILLED only when candle.close
    enters the zone. Wick entries do NOT trigger fill (FR-007).
    """
    top: float
    bottom: float
    midpoint: float
    direction: Direction
    status: FVGStatus
    candle_index: int


@dataclass
class OrderBlock:
    """The last opposing candle before a BOS — used as a precise entry zone.

    Bullish OB: last bearish candle (close < open) immediately before bullish BOS.
    Bearish OB: last bullish candle (close > open) immediately before bearish BOS.
    Boundaries use candle body only — max/min of open and close; wicks excluded (FR-012).

    State transitions:
        ACTIVE → TESTED:      candle wick enters zone (candle.low <= ob.top for bullish OB)
        TESTED → INVALIDATED: candle close-through in opposite direction
        ACTIVE → INVALIDATED: fast close-through with no prior wick test (D-007)
    """
    top: float
    bottom: float
    direction: Direction
    status: OBStatus
    candle_index: int


@dataclass
class LiquiditySweep:
    """A stop-hunt event that wicks beyond equal highs/lows and closes back inside.

    Sweep High: candle wick exceeds equal highs AND same candle closes back below (FR-014).
    Sweep Low:  candle wick breaks below equal lows AND same candle closes back above (FR-015).
    """
    sweep_level: float   # Price of the equal high/low that was swept
    close_price: float   # Candle close price after the wick exceeded the level
    type: SweepType
    candle_index: int


@dataclass
class EntrySignal:
    """Final scored output from one generate_signal() call.

    Invariants enforced by scorer.py and smc_engine.py:
    - direction == NONE  when confidence < CONFIDENCE_THRESHOLD (FR-019)
    - direction == NONE  when fewer than min_candles bars provided
    - entry_zone_top == entry_zone_bottom == 0.0  when direction == NONE
    - reason is always populated, even for NONE signals
    - confidence is clipped to [0.0, 1.0]
    """
    direction: Direction
    confidence: float
    entry_zone_top: float
    entry_zone_bottom: float
    reason: str
    components: list[str] = field(default_factory=list)
    signal_type: SignalType = field(default=SignalType.NONE)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    h4_bias: Bias = field(default=Bias.NEUTRAL)
    h4_bias_strength: float = field(default=0.0)
