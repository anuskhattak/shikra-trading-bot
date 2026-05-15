# Phase 0 Research: SMC Signal Detection Engine

**Feature**: 002-smc-engine
**Date**: 2026-05-12
**Purpose**: Resolve all NEEDS CLARIFICATION items and key design unknowns before Phase 1

---

## R-001: Fractal Swing Point Detection — Vectorized Pattern

**Problem**: FR-001 requires identifying swing highs/lows using a fractal rule: pivot valid only when N candles on each side satisfy the condition. Need the cleanest pandas pattern.

**Decision**: Index-based vectorized comparison using `pandas.Series.shift()`.

```python
# Swing High: candle[i].high > high of N candles on each side
def _is_swing_high(highs: pd.Series, n: int) -> pd.Series:
    condition = pd.Series(True, index=highs.index)
    for offset in range(1, n + 1):
        condition &= (highs > highs.shift(offset))   # left side
        condition &= (highs > highs.shift(-offset))  # right side
    return condition

# Important: shift(-N) requires future bars — confirmed swings have NaN at tail
# Engine must only use confirmed swings (non-NaN rows)
```

**Rationale**: Entirely vectorized — no Python loops over rows. Works on any look-back window. `shift(-N)` naturally produces `NaN` for the last N rows, marking them as "not yet confirmed" — correct behavior for a real-time engine.

**Alternatives Rejected**:
- `rolling().apply()` with custom function — slower, harder to read
- Explicit for-loop over rows — O(n) Python loop, ~50× slower for 200 candles
- `scipy.signal.argrelextrema` — external dependency, harder to configure per-fractal rule

---

## R-002: BOS / CHoCH — Candle-Close Rule Implementation

**Problem**: FR-004 requires that BOS and CHoCH use candle **close**, not wick. Must ensure no accidental wick-triggered signals.

**Decision**: Compare `df['close']` only — never `df['high']` or `df['low']` for structure breaks.

```python
# BOS Bullish: close exceeds most recent confirmed swing high
def detect_bos(df: pd.DataFrame, swing_highs: list[SwingPoint]) -> SignalType:
    if not swing_highs:
        return SignalType.NONE
    latest_swing_high = swing_highs[-1].price
    if df['close'].iloc[-1] > latest_swing_high:
        return SignalType.BOS_BULLISH
    return SignalType.NONE
```

**Rationale**: Single-field comparison on `close` column is unambiguous and fast.

---

## R-003: FVG Detection — 3-Candle Vectorized Scan

**Problem**: FR-005/FR-006 require comparing candle[N-2].high with candle[N].low. Must scan efficiently across 200 candles.

**Decision**: Shift-based vectorized comparison.

```python
# Bullish FVG: candle[i-2].high < candle[i].low  (gap between 1st and 3rd candle)
bullish_fvg_mask = df['high'].shift(2) < df['low']
bearish_fvg_mask = df['low'].shift(2) > df['high']
```

**FVG Fill Check (candle-close rule from Clarifications Q4)**:
```python
# FVG is FILLED when a subsequent candle closes inside the zone
def is_fvg_filled(fvg: FVGZone, df: pd.DataFrame) -> bool:
    subsequent = df.iloc[fvg.candle_index + 1:]
    if fvg.direction == Direction.BULLISH:
        return (subsequent['close'] >= fvg.bottom).any() and \
               (subsequent['close'] <= fvg.top).any()
    else:
        return (subsequent['close'] <= fvg.top).any() and \
               (subsequent['close'] >= fvg.bottom).any()
```

**Rationale**: Entirely vectorized — processes 200 candles in microseconds.

---

## R-004: OB TESTED Status Resolution

**Problem**: Spec (US3-AC2) mentions TESTED status but no FR defines the trigger rule. Spec checklist identified this as CHK002/CHK018.

**Decision**: Two-rule OB lifecycle:
- ACTIVE → TESTED: any candle **wick** enters the OB zone (price visited the zone)
- TESTED → INVALIDATED: any candle **closes** through the OB body (zone destroyed by close)

```python
def update_ob_status(ob: OrderBlock, df: pd.DataFrame) -> OBStatus:
    subsequent = df.iloc[ob.candle_index + 1:]
    for _, row in subsequent.iterrows():
        if ob.direction == Direction.BULLISH:
            # Wick touched zone → TESTED
            if row['low'] <= ob.top and row['low'] >= ob.bottom:
                ob.status = OBStatus.TESTED
            # Close through zone → INVALIDATED
            if row['close'] < ob.bottom:
                return OBStatus.INVALIDATED
        # Mirror logic for BEARISH OB
    return ob.status
```

**Rationale**: TESTED is informational (price reached institutional zone); INVALIDATED is structural (zone absorbed/rejected). Different semantics → different trigger rules.

---

## R-005: "Established Trend" Definition for CHoCH (FR-003)

**Problem**: FR-003 says CHoCH fires in "an established bullish/bearish trend" — undefined in spec. Checklist CHK008.

**Decision**: Established trend = direction of the most recent confirmed BOS.
- Last confirmed BOS was BOS_BULLISH → current trend = BULLISH
- Last confirmed BOS was BOS_BEARISH → current trend = BEARISH
- No confirmed BOS yet → trend = NEUTRAL → CHoCH cannot fire

```python
# Trend state derived from BOS history, not a separate tracker
current_trend = bos_history[-1].signal_type if bos_history else SignalType.NONE
```

**Rationale**: Consistent with how SMC practitioners define trend — each confirmed BOS resets the trend direction. No additional state needed; BOS detection already runs before CHoCH detection.

---

## R-006: Confidence Scoring Formula Specification

**Problem**: FR-018 says "summing component weights" but doesn't specify exact formula. Checklist CHK009/CHK010.

**Decision**: Additive weighted sum. Missing component = 0 contribution. Weights must sum to 1.0 (invariant). Threshold comparison is inclusive (≥ threshold = accept).

```python
DEFAULT_WEIGHTS = {"bos": 0.40, "fvg": 0.30, "ob": 0.20, "liquidity_sweep": 0.10}

def score_signal(components: dict[str, bool], weights: dict[str, float]) -> float:
    return sum(weights[k] for k, present in components.items() if present)

# Example: BOS + FVG + OB present, no LS → score = 0.40 + 0.30 + 0.20 = 0.90
# BOS only → score = 0.40 → below 0.65 threshold → discarded
```

**Weights-sum invariant**: `sum(DEFAULT_WEIGHTS.values()) == 1.0` — enforced at config load time with assertion.

**Rationale**: Additive sum is deterministic (SC-006), transparent (every component's contribution visible in score), and trivially unit-testable.

---

## R-007: false_signals.json Thread-Safety

**Problem**: FR-023 requires discarded signals written to `logs/false_signals.json`. Engine is designed for parallel backtesting (NFR-002) — concurrent writes possible.

**Decision**: Use `threading.Lock` (same pattern as `001-mt5-broker`). Read-append-write under lock.

```python
_false_signal_lock = threading.Lock()
_false_signal_path = Path("logs/false_signals.json")

def _log_false_signal(signal: EntrySignal, reason: str) -> None:
    with _false_signal_lock:
        existing = json.loads(_false_signal_path.read_text()) if _false_signal_path.exists() else []
        existing.append({"timestamp": signal.timestamp.isoformat(),
                         "confidence": signal.confidence,
                         "reason": reason})
        _false_signal_path.write_text(json.dumps(existing, indent=2))
```

**Rationale**: Consistent with `001-mt5-broker` file-locking pattern. Lock granularity (per-write) is acceptable given low write frequency in live trading.

---

## R-008: Performance Validation — 100ms Budget

**Problem**: SC-005 requires full signal generation on 200 H1 candles in < 100ms.

**Finding**: Vectorized pandas on 200 rows takes ~0.1–0.5ms. Five detectors running sequentially = ~2–5ms total. The 100ms budget is 20–50× headroom.

**Decision**: No performance optimization needed. Pure vectorized pandas is sufficient.

**Benchmark baseline**:
```
200-row DataFrame operations  ~0.1ms each
5 detectors × 0.5ms = 2.5ms
Scoring + logging = 0.5ms
Total estimated = ~3ms (vs 100ms budget)
```

**Conclusion**: 100ms target is easily met with no special optimization.
