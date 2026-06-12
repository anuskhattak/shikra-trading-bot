# Data Model: H4 Bias Engine

**Feature**: 007-h4-bias-engine  
**Date**: 2026-06-12

---

## New Entities

### H4BiasResult

Immutable output of one H4 bias analysis cycle.

| Field | Type | Description | Constraints |
|-------|------|-------------|------------|
| `bias` | `Bias` (enum) | Classified H4 direction | BULLISH / BEARISH / RANGING |
| `strength` | `float` | Conviction score for the bias | 0.0 – 1.0 |
| `swing_count` | `int` | Confirmed fractal swings used | ≥ 0; 0 on cold start |
| `timestamp` | `datetime` | UTC time of calculation | always set |

**Validation rules**:
- `strength` clipped to [0.0, 1.0]
- `bias == RANGING` when `swing_count < 2` (cold start)
- Frozen dataclass — immutable after creation

---

## Modified Entities

### Bias (enum) — `src/engine/models.py`

**Existing values** (unchanged):
- `BULLISH = "BULLISH"`
- `BEARISH = "BEARISH"`
- `NEUTRAL = "NEUTRAL"`

**New value added**:
- `RANGING = "RANGING"` — H4 structure analyzed; market is consolidating; blocks all trades

---

### EntrySignal — `src/engine/models.py`

**Existing fields** (unchanged): `direction`, `confidence`, `entry_zone_top`, `entry_zone_bottom`, `reason`, `components`, `signal_type`, `timestamp`

**New fields added** (at end, with defaults):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `h4_bias` | `Bias` | `Bias.NEUTRAL` | H4 bias active when signal was generated |
| `h4_bias_strength` | `float` | `0.0` | H4 bias conviction score at signal time |

---

### PipelineContext — `src/orchestrator/models.py`

**New optional field added**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `h4_bias_result` | `Optional[H4BiasResult]` | `None` | Populated by Stage 0 of run_pipeline() |

---

## Entity Relationships

```
H4BiasService
    │
    │ refresh(h4_bars) →
    ▼
H4BiasResult ──────────────── stored in ──── PipelineContext.h4_bias_result
    │                                                │
    │ bias, strength passed to                       │
    ▼                                                ▼
score_and_assemble()                         backtest metrics / audit log
    │
    │ embedded in
    ▼
EntrySignal.h4_bias
EntrySignal.h4_bias_strength
```

---

## State Transitions

### H4BiasService internal state

```
UNINITIALISED
    │ first refresh() called
    ▼
READY (last_result = H4BiasResult)
    │ each new H4 bar → refresh()
    ▼
READY (last_result updated)
```

### H4BiasResult.bias state machine

```
RANGING (cold start / insufficient data)
    │ enough bars + clear structure
    ▼
BULLISH ──── structure breaks ──── RANGING
    │                                 │
    │ LH/LL sequence confirmed         │ HH/HL sequence confirmed
    ▼                                 ▼
BEARISH ◄──────────── (direct transition possible) ──────────────►BULLISH
```

---

## Config Schema

New section added to `config.yaml`:

```yaml
analysis:
  h4_bias:
    lookback_bars: 20              # H4 bars to scan for swing points
    fractal_n: 2                   # candles on each side for fractal confirmation
    bullish_strength_threshold: 0.60
    bearish_strength_threshold: 0.60

smc_engine:
  weights:
    bos_or_choch:   0.40
    fvg:            0.30
    order_block:    0.20
    liquidity_sweep: 0.10
    h4_alignment:   0.20           # NEW: added when H4 aligns with H1 signal
    mtf_boost:      1.30           # NEW: multiplier applied when h4_alignment triggered
```
