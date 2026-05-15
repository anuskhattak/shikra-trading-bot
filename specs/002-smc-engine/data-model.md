# Data Model: SMC Signal Detection Engine

**Feature**: 002-smc-engine
**Date**: 2026-05-12

---

## Enums

### 1. Bias
```
BULLISH   — Higher-timeframe directional bias is bullish (passed by caller)
BEARISH   — Higher-timeframe directional bias is bearish
NEUTRAL   — No directional bias; engine generates signals in any direction
```
**Source**: Caller-provided (`htf_bias` argument). Engine does not derive it (FR-021).

---

### 2. Direction
```
LONG    — Bullish signal; buyer entry
SHORT   — Bearish signal; seller entry
NONE    — No valid setup found
```

---

### 3. SignalType
```
BOS_BULLISH    — Break of Structure upward (bullish trend continuation)
BOS_BEARISH    — Break of Structure downward (bearish trend continuation)
CHOCH_BULLISH  — Change of Character upward (reversal from bearish → bullish)
CHOCH_BEARISH  — Change of Character downward (reversal from bullish → bearish)
NONE           — No structure event detected
```

---

### 4. FVGStatus
```
UNFILLED  — Gap has not been revisited by price (active entry zone)
FILLED    — A subsequent candle closed inside the zone (zone consumed)
```
**Transition rule**: UNFILLED → FILLED when `candle.close` is inside zone boundaries. Wick entries do not trigger fill (Clarifications Q4, FR-007).

---

### 5. OBStatus
```
ACTIVE       — OB detected; price has not returned to the zone
TESTED       — A candle wick entered the OB zone (price visited it)
INVALIDATED  — A candle closed through the OB body in the opposite direction
```
**Transitions**:
```
ACTIVE → TESTED:      candle.low <= ob.top (bullish OB wick entry)
TESTED → INVALIDATED: candle.close < ob.bottom (bullish OB close-through)
ACTIVE → INVALIDATED: close-through without prior wick test (fast move)
```

---

### 6. SweepType
```
HIGH  — Sweep above equal highs (stop hunt above resistance)
LOW   — Sweep below equal lows (stop hunt below support)
```

---

## Entities

### 7. SwingPoint
| Field | Type | Constraint |
|-------|------|-----------|
| price | float | Price level of the pivot |
| candle_index | int | Index into the input DataFrame |
| type | str | `"HIGH"` or `"LOW"` |
| confirmed | bool | True only when N candles on both sides satisfy fractal rule |
| fractal_n | int | Number of confirmation candles used (default 2) |

**Detection rule (FR-001)**: Pivot confirmed when `N` consecutive candles on each side have strictly lower highs (swing high) or strictly higher lows (swing low). Unconfirmed pivots are discarded.

---

### 8. FVGZone
| Field | Type | Constraint |
|-------|------|-----------|
| top | float | Upper boundary of gap (candle[N].low for bullish FVG) |
| bottom | float | Lower boundary of gap (candle[N-2].high for bullish FVG) |
| midpoint | float | (top + bottom) / 2 |
| direction | Direction | LONG (bullish FVG) or SHORT (bearish FVG) |
| status | FVGStatus | UNFILLED on creation; FILLED when close enters zone |
| candle_index | int | Index of candle[N] (the third candle of the 3-candle pattern) |

**Detection rule (FR-005/FR-006)**:
- Bullish FVG: `candle[N-2].high < candle[N].low`
- Bearish FVG: `candle[N-2].low > candle[N].high`

---

### 9. OrderBlock
| Field | Type | Constraint |
|-------|------|-----------|
| top | float | OB body upper boundary (candle body high = max(open, close)) |
| bottom | float | OB body lower boundary (candle body low = min(open, close)) |
| direction | Direction | LONG (bullish OB) or SHORT (bearish OB) |
| status | OBStatus | ACTIVE on creation |
| candle_index | int | Index of the OB candle in the input DataFrame |

**Detection rule (FR-009/FR-010)**:
- Bullish OB: last bearish candle (`close < open`) immediately before a bullish BOS
- Bearish OB: last bullish candle (`close > open`) immediately before a bearish BOS

**Boundaries**: Use candle body only — `open` and `close`. Wicks excluded (FR-012).

---

### 10. LiquiditySweep
| Field | Type | Constraint |
|-------|------|-----------|
| sweep_level | float | Price of the equal high/low that was swept |
| close_price | float | Candle close price after the wick exceeded the level |
| type | SweepType | HIGH or LOW |
| candle_index | int | Index of the sweep candle |

**Detection rule (FR-013/FR-014/FR-015)**:
- Equal highs: two or more candle highs within `pip_tolerance` (default 5 pips = $0.50)
- Sweep High: candle wick exceeds equal highs AND candle closes back below them — all within same candle
- Sweep Low: candle wick breaks below equal lows AND closes back above them

---

### 11. EntrySignal *(engine output)*
| Field | Type | Constraint |
|-------|------|-----------|
| direction | Direction | LONG, SHORT, or NONE |
| confidence | float | 0.0–1.0; additive sum of component weights |
| entry_zone_top | float | Upper boundary of entry zone (OB top if present; FVG top otherwise) |
| entry_zone_bottom | float | Lower boundary of entry zone (OB bottom if present; FVG bottom otherwise) |
| reason | str | Human-readable components string (e.g., `"BOS_BULLISH + FVG + OB + Liquidity Sweep"`) |
| components | list[str] | Machine-readable list of detected components (for downstream audit) |
| signal_type | SignalType | The structural event that triggered the signal |
| timestamp | datetime | UTC timestamp of signal generation |

**Invariants**:
- `direction == NONE` when `confidence < CONFIDENCE_THRESHOLD` (FR-019)
- `direction == NONE` when fewer than 50 candles provided (Assumption 2)
- `entry_zone_top` and `entry_zone_bottom` are both 0.0 when `direction == NONE`
- `reason` always populated, even for NONE signals

---

## Confidence Scoring Formula

```
confidence = Σ(weight_i  ×  1 if component_i present else 0)

Default weights (config.yaml / Assumption 4):
  bos_or_choch:     0.40  (required — base signal)
  fvg:              0.30  (primary entry zone)
  order_block:      0.20  (precise entry level)
  liquidity_sweep:  0.10  (reversal confirmation bonus)

Invariant: sum(weights) == 1.0

Threshold: confidence >= 0.65 → signal accepted (CONFIDENCE_THRESHOLD in config.yaml)
```

**Examples**:
| Components | Score | Decision |
|-----------|-------|----------|
| BOS + FVG + OB + LS | 1.00 | Accept |
| BOS + FVG + OB | 0.90 | Accept |
| BOS + FVG | 0.70 | Accept |
| BOS + OB | 0.60 | Reject (logged) |
| BOS only | 0.40 | Reject (logged) |

---

## State Transitions Summary

```
FVGZone:    UNFILLED ──(close inside zone)──→ FILLED

OrderBlock: ACTIVE ──(wick enters zone)──→ TESTED ──(close through body)──→ INVALIDATED
            ACTIVE ──(close through body, no prior test)──────────────────→ INVALIDATED

EntrySignal: Generated fresh on every engine call. No persistent state.
```

---

## Config Schema (config.yaml)

```yaml
smc_engine:
  fractal_n: 2                    # Swing point confirmation window (candles each side)
  lookback_window: 20             # Candles to scan for swing points
  equal_level_tolerance_pips: 5   # Equal highs/lows tolerance (5 pips = $0.50 XAUUSD)
  confidence_threshold: 0.65      # Minimum score to generate a signal
  weights:
    bos_or_choch: 0.40
    fvg: 0.30
    order_block: 0.20
    liquidity_sweep: 0.10
  min_candles: 50                 # Minimum bars required for detection
```
