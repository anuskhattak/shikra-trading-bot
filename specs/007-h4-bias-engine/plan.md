# Implementation Plan: H4 Bias Engine

**Branch**: `007-h4-bias-engine` | **Date**: 2026-06-12 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/007-h4-bias-engine/spec.md`

---

## Summary

Implement `H4BiasService` in `src/analysis/h4_bias.py` that classifies H4 directional structure as BULLISH / BEARISH / RANGING using fractal swing-point sequences. Output feeds the signal scoring pipeline via a +0.20 alignment weight and 1.3x MTF multiplier; RANGING blocks all trade entry. Reuses the existing `detect_swing_points()` fractal detector from `src/engine/swing.py`. Five files are modified (models, scorer, pipeline, orchestrator models, analysis `__init__`); one new file is created (`h4_bias.py`).

---

## Technical Context

**Language/Version**: Python 3.10+  
**Primary Dependencies**: pandas, numpy, loguru — all already in requirements.txt  
**Storage**: Stateful in-memory cache (same pattern as `ATRService`); no persistence  
**Testing**: pytest with fixtures; unit tests mirror `test_atr_calibration.py` pattern  
**Target Platform**: Windows/Linux — runs inside the bot process alongside ATRService  
**Project Type**: Single Python project under `src/`  
**Performance Goals**: H4 bias recalculation completes within the same H4 bar-close event (< 50ms on 200 bars)  
**Constraints**: No MT5 imports in analysis layer; caller pre-fetches OHLCV (same as ATRService D-005)

---

## Constitution Check

*GATE: Must pass before Phase 0 research.*

| Gate | Status | Notes |
|------|--------|-------|
| Reuses existing `detect_swing_points()` | ✅ PASS | No duplicate swing detection logic |
| New file under `src/analysis/` — correct package | ✅ PASS | Mirrors `atr_service.py` placement |
| No MT5 import in analysis layer | ✅ PASS | Bars passed in by caller |
| Modifies `EntrySignal` — downstream compatibility | ✅ PASS | New fields have defaults; zero breaking changes |
| `Bias.RANGING` added to existing enum | ✅ PASS | `Bias.NEUTRAL` retained; scorer updated |
| No dashboard / monitoring scope creep | ✅ PASS | Pure analysis + signal scoring |

---

## Project Structure

### Documentation (this feature)

```text
specs/007-h4-bias-engine/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── contracts/
│   ├── h4_bias_service.md     ← H4BiasService API contract
│   └── scorer_extension.md    ← score_and_assemble extension contract
└── tasks.md             ← Phase 2 output (/sp.tasks command)
```

### Source Code Changes

```text
src/
├── analysis/
│   ├── h4_bias.py          ← NEW: H4BiasService, H4BiasResult, classify_bias()
│   └── __init__.py         ← UPDATE: export H4BiasService, H4BiasResult
│
├── engine/
│   ├── models.py           ← UPDATE: add Bias.RANGING; add h4_bias + h4_bias_strength to EntrySignal
│   └── scorer.py           ← UPDATE: h4_alignment boost + MTF multiplier + RANGING block
│
└── orchestrator/
    ├── models.py           ← UPDATE: add h4_bias_result: Optional[H4BiasResult] to PipelineContext
    └── pipeline.py         ← UPDATE: Stage 0 H4 bias refresh; pass bias to generate_signal()

tests/
└── test_h4_bias.py         ← NEW: unit tests for H4BiasService and classify_bias()
```

**Structure Decision**: Single project layout. New file goes into `src/analysis/` (same package as `ATRService`). Minimal footprint — 1 new file, 5 modified files.

---

## Design Decisions (Phase 0 Research)

See [research.md](./research.md) for full rationale. Key decisions:

| Decision | Choice | Why |
|----------|--------|-----|
| Bias classification algorithm | Fractal swing HH/HL vs LH/LL sequence | Consistent with existing `detect_swing_points()` fractal rule |
| Swing reuse | Call `detect_swing_points()` from `src/engine/swing.py` | Already tested, fractal-confirmed — no duplication |
| Bias enum location | Extend existing `Bias` in `src/engine/models.py` | Scorer already imports `Bias`; one source of truth |
| RANGING value | New `Bias.RANGING` (keep `Bias.NEUTRAL` for non-H4 callers) | Semantic difference: NEUTRAL = no bias info, RANGING = actively consolidating |
| Alignment boost in scorer | Add `h4_alignment` weight key; apply before threshold check | Mirrors existing component weight pattern |
| MTF multiplier | Applied to post-alignment confidence before threshold | Boost should affect accept/reject decision |
| RANGING block | Explicit early return in scorer before all other checks | Fastest path; logs to false_signals.json with `H4_RANGING` reason |
| EntrySignal fields | Add `h4_bias: Bias` + `h4_bias_strength: float` with defaults | Zero breaking changes to callers; audit trail in signal |
| LSTM replaceability | `H4BiasService.refresh()` returns `H4BiasResult` — interface is the contract | Swap to LSTM service in spec012 without changing pipeline |

---

## Implementation Phases

### Phase A — Models Update (`src/engine/models.py`)

1. Add `RANGING = "RANGING"` to `Bias` enum
2. Add `h4_bias: Bias = field(default=Bias.NEUTRAL)` to `EntrySignal`
3. Add `h4_bias_strength: float = 0.0` to `EntrySignal`

**Risk**: Callers that construct `EntrySignal` with positional args will break if fields are inserted mid-list. Mitigation: add new fields at the **end** of the dataclass with defaults.

---

### Phase B — H4 Bias Service (`src/analysis/h4_bias.py`) — NEW FILE

**`H4BiasResult` dataclass:**
```python
@dataclass(frozen=True)
class H4BiasResult:
    bias:           Bias        # BULLISH | BEARISH | RANGING
    strength:       float       # 0.0–1.0 conviction score
    swing_count:    int         # number of confirmed swings used
    timestamp:      datetime
```

**`classify_bias(swing_points: list[SwingPoint]) -> tuple[Bias, float]`:**
- Separate highs and lows from swing_points list
- Count HH (each high > previous high) and HL (each low > previous low) for BULLISH
- Count LH (each high < previous high) and LL (each low < previous low) for BEARISH
- Strength = (qualifying pairs / total pairs checked)
- Thresholds (configurable): strength >= 0.6 → BULLISH/BEARISH; else RANGING

**`H4BiasService` class:**
- `__init__(config: dict)` — reads `analysis.h4_bias` config section
- `refresh(h4_bars: list[OHLCVBar]) -> H4BiasResult` — calls `detect_swing_points()` then `classify_bias()`; updates internal cache; never raises
- `get_bias() -> H4BiasResult` — returns last result (or RANGING/0.0 if no data yet)
- `is_ready() -> bool` — True once first successful refresh completed
- Cold start (< lookback bars) → returns `H4BiasResult(bias=Bias.RANGING, strength=0.0, swing_count=0)`

---

### Phase C — Scorer Update (`src/engine/scorer.py`)

Modify `score_and_assemble()` signature and logic:

```python
def score_and_assemble(
    ...
    htf_bias: Bias,
    htf_bias_strength: float = 0.0,   # NEW param
) -> EntrySignal:
```

**New logic (inserted before existing HTF bias check):**

```python
# RANGING blocks all trades before scoring (FR-007 equivalent in scorer)
if htf_bias == Bias.RANGING:
    return _log_and_discard(f"{reason} [H4_RANGING]", 0.0, signal_type, now)

# H4 alignment boost — added when bias matches signal direction
if (htf_bias == Bias.BULLISH and direction == Direction.LONG) or \
   (htf_bias == Bias.BEARISH and direction == Direction.SHORT):
    confidence += float(weights.get("h4_alignment", 0.20))
    confidence = min(1.0, confidence)
    components.append("H4_ALIGN")
    # MTF multiplier applied after alignment boost
    mtf_factor = float(weights.get("mtf_boost", 1.3))
    confidence = min(1.0, confidence * mtf_factor)
```

**`EntrySignal` population:** Set `h4_bias=htf_bias, h4_bias_strength=htf_bias_strength` on the returned signal.

---

### Phase D — Pipeline Update (`src/orchestrator/pipeline.py`)

Add `H4BiasService` as a required dependency:

```python
def run_pipeline(
    ctx: PipelineContext,
    atr_service: ATRService,
    h4_bias_service: H4BiasService,   # NEW param
    config: dict,
) -> PipelineContext:
```

**New Stage 0 (before ATR refresh):**
```python
# Stage 0: H4 bias refresh
h4_bars = ctx.bars.get(Timeframe.H4, [])
if h4_bars:
    h4_result = h4_bias_service.refresh(h4_bars)
    ctx.h4_bias_result = h4_result
```

**Stage 2 update:** Replace `htf_bias=Bias.NEUTRAL` with actual bias:
```python
bias = ctx.h4_bias_result.bias if ctx.h4_bias_result else Bias.NEUTRAL
strength = ctx.h4_bias_result.strength if ctx.h4_bias_result else 0.0
ctx.entry_signal = generate_signal(df, htf_bias=bias, htf_bias_strength=strength, config=config.get("smc_engine"))
```

**Note:** `generate_signal()` in `smc_engine.py` passes `htf_bias` through to `score_and_assemble()` — verify `htf_bias_strength` is threaded through there too (may require `smc_engine.py` update).

---

### Phase E — Orchestrator Models Update (`src/orchestrator/models.py`)

Add to `PipelineContext`:
```python
from src.analysis.h4_bias import H4BiasResult
...
h4_bias_result: Optional[H4BiasResult] = None
```

---

### Phase F — Config Schema Update

Add to `config.yaml` under `analysis`:
```yaml
analysis:
  atr:
    ...  # existing
  h4_bias:
    lookback_bars: 20          # H4 swing lookback window
    fractal_n: 2               # fractal confirmation candles each side
    bullish_strength_threshold: 0.6
    bearish_strength_threshold: 0.6
```

Add to `smc_engine` config:
```yaml
smc_engine:
  weights:
    bos_or_choch: 0.40
    fvg: 0.30
    order_block: 0.20
    liquidity_sweep: 0.10
    h4_alignment: 0.20         # NEW
    mtf_boost: 1.30            # NEW multiplier (not additive)
```

---

### Phase G — Tests (`tests/test_h4_bias.py`)

| Test | Coverage |
|------|---------|
| `test_bullish_bias_hh_hl` | 4 swings making HH+HL → BULLISH, strength > 0.6 |
| `test_bearish_bias_lh_ll` | 4 swings making LH+LL → BEARISH, strength > 0.6 |
| `test_ranging_no_clear_structure` | Mixed swings → RANGING, strength < 0.5 |
| `test_cold_start_insufficient_bars` | < lookback bars → RANGING, strength=0.0, no exception |
| `test_ranging_blocks_scorer` | RANGING bias → scorer returns NONE signal with `H4_RANGING` reason |
| `test_alignment_boost_added` | BULLISH bias + LONG signal → confidence includes h4_alignment |
| `test_mtf_multiplier_applied` | BULLISH bias + LONG signal → confidence × 1.3 applied |
| `test_entry_signal_carries_bias` | EntrySignal.h4_bias and h4_bias_strength populated |
| `test_pipeline_wires_h4_service` | run_pipeline() uses H4BiasService; mock returns BULLISH |

---

## Dependency Map

```
spec006 (ATRService) ──────────────────┐
spec002 (swing.detect_swing_points()) ─┤
                                        ▼
                             H4BiasService  (NEW — spec007)
                                        │
                          ┌─────────────┴──────────────┐
                          ▼                            ▼
                   scorer.py (UPDATE)         pipeline.py (UPDATE)
                          │
                          ▼
                   EntrySignal (UPDATE)
                          │
                          ▼
                   BacktestEngine / ExecutionEngine (spec009 / spec005)
                          │
                          ▼
                   H4BiasService ← LSTM replacement (spec012)
```

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| `smc_engine.generate_signal()` doesn't thread `htf_bias_strength` to scorer | High | Medium | Audit `smc_engine.py` before Phase C; add param if needed |
| Backtest engine calls `run_pipeline()` with 2-arg signature | High | High | Update all callers of `run_pipeline()` to pass `h4_bias_service` |
| Cold-start RANGING means first N H4 bars never trade | Low | Low | Expected behavior; document in quickstart |
| `Bias.RANGING` addition breaks exhaustive match in future code | Low | Low | Add `# noqa` or update any existing `match` statements |
