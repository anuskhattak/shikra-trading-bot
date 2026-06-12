# Data Model: ATR Calibration Module

**Feature**: 006-atr-calibration  
**Date**: 2026-05-22

---

## Entities

### `Timeframe` (Enum)

Represents a trading timeframe. Numeric value = MT5 timeframe constant for direct broker passthrough.

| Member | Value | Description |
|--------|-------|-------------|
| M5     | 5     | 5-minute bars |
| H1     | 16385 | 1-hour bars |
| H4     | 16388 | 4-hour bars |
| D1     | 16408 | Daily bars |

---

### `OHLCVBar` (Dataclass — input)

Source data for ATR computation. Comes from `market_data.py` (spec001).

| Field | Type | Constraints |
|-------|------|-------------|
| `open` | float | > 0 |
| `high` | float | > 0, ≥ low |
| `low` | float | > 0, ≤ high |
| `close` | float | > 0 |
| `volume` | float | ≥ 0 |
| `timestamp` | datetime | UTC, non-null |

**Validation rule**: Bar is rejected if `high < low` OR `close <= 0`.

---

### `VolatilityRegime` (Enum)

Derived from ATR ratio (`current_atr / reference_atr`). Thresholds configured in `config.yaml` (reused from spec004).

| Member | Condition |
|--------|-----------|
| LOW | ratio < 0.7 |
| NORMAL | 0.7 ≤ ratio < 2.0 |
| EXTREME | ratio ≥ 2.0 |

---

### `AdaptiveMultipliers` (Dataclass)

SL and TP multipliers selected for the current `VolatilityRegime`.

| Field | Type | Default (NORMAL) | Description |
|-------|------|-----------------|-------------|
| `sl_multiplier` | float | 1.5 | Multiplies D1 ATR to get SL distance |
| `tp_multiplier` | float | 3.0 | Multiplies SL distance to get TP distance |
| `regime` | VolatilityRegime | NORMAL | Regime that produced these multipliers |

**Per-regime defaults** (all configurable):

| Regime | `sl_multiplier` | `tp_multiplier` |
|--------|----------------|----------------|
| LOW | 1.0 | 2.0 |
| NORMAL | 1.5 | 3.0 |
| EXTREME | 2.0 | 4.0 |

---

### `ATRReading` (Dataclass)

Represents a single computed ATR result for a given timeframe.

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `timeframe` | Timeframe | No | Which timeframe this reading is for |
| `current_atr` | float | Yes | Most recently computed ATR (None if insufficient data) |
| `reference_atr` | float | Yes | Rolling average of last 20 ATR values (None if insufficient history) |
| `ratio` | float | Yes | current_atr / reference_atr (None if either is None) |
| `bar_count` | int | No | Number of valid bars used for computation |
| `timestamp` | datetime | No | UTC time of computation |

**Invariants**:
- `current_atr` is None **or** > 0
- `ratio` is None **or** > 0
- `bar_count` ≥ 0

---

### `ATRCache` (Dataclass)

Per-timeframe cache entry.

| Field | Type | Description |
|-------|------|-------------|
| `reading` | ATRReading | Last successfully computed reading |
| `is_fresh` | bool | True = computed from latest closed bar; False = stale |
| `last_refreshed` | datetime | UTC timestamp of last successful refresh |

**State transitions**:

```
[EMPTY] ──refresh(bars)──► [FRESH]
[FRESH] ──new bar signal──► [STALE]
[STALE] ──refresh(bars)──► [FRESH]
[STALE] ──refresh fails──► [STALE] (last reading preserved, failure logged)
```

---

## Relationships

```
ATRService
  │
  ├── dict[Timeframe → ATRCache]
  │         │
  │         └── ATRCache.reading: ATRReading
  │                     │
  │                     ├── current_atr  ──► lot_calculator.calculate_sl_price()  [D1]
  │                     ├── reference_atr ──► volatility_filter.check_volatility() [H1]
  │                     └── ratio        ──► VolatilityRegime classification
  │
  └── get_adaptive_multipliers(regime) ──► AdaptiveMultipliers
                                              │
                                              ├── sl_multiplier ──► lot_calculator
                                              └── tp_multiplier ──► lot_calculator
```

---

## Validation Rules Summary

| Rule | Source | Enforced in |
|------|--------|------------|
| High ≥ Low | FR-012 | `validate_ohlcv_bars()` |
| Close > 0 | FR-012 | `validate_ohlcv_bars()` |
| ATR period ≥ 1 | config | `compute_atr()` |
| Reference period ≥ 1 | config | `compute_reference_atr()` |
| current_atr > 0 | D-007 | `ATRReading` construction |
| Regime thresholds: LOW < NORMAL < EXTREME | config | `get_adaptive_multipliers()` |
