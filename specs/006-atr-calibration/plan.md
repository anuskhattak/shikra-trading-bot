# Implementation Plan: ATR Calibration Module

**Branch**: `006-atr-calibration` | **Date**: 2026-05-22 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/006-atr-calibration/spec.md`

---

## Summary

Build `src/analysis/` — the ATR computation layer that feeds three downstream modules. The module computes True Range and ATR for four timeframes (M5, H1, H4, D1), maintains a per-timeframe in-memory cache refreshed on each bar close, derives a rolling reference ATR (20-period) as the baseline for volatility ratio classification, and returns adaptive SL/TP multipliers based on the current `VolatilityRegime`. It serves as the missing bridge between raw OHLCV data (spec001) and the volatility filter (spec004) and lot calculator (spec003), which currently accept ATR as external input parameters with no computation source.

---

## Technical Context

**Language/Version**: Python 3.10+  
**Primary Dependencies**: loguru (already present), pytest, pytest-mock (already present) — zero new dependencies  
**Storage**: In-memory only; no disk persistence (Assumption: cache rebuilt on startup from MT5 historical data)  
**Testing**: pytest — all unit tests are pure (no MT5 required); ATR module has no broker dependency (D-005)  
**Target Platform**: Windows (MT5 Python SDK is Windows-only for broker integration; ATR module itself is platform-agnostic)  
**Project Type**: single  
**Performance Goals**: ATR refresh < 1 second on bar close (SC-003); all intra-bar requests served from cache with zero recomputation (SC-002)  
**Constraints**: No MT5 imports in `src/analysis/`; XAUUSD only; simple arithmetic average ATR (not Wilder's EMA) for test determinism; all thresholds and multipliers configurable via `config.yaml`

---

## Constitution Check

*GATE: Checked against CLAUDE.md core guarantees.*

| Guarantee | Requirement | Status |
|-----------|-------------|--------|
| Signal Integrity | ATR values within ±0.1% of reference calculation | ✅ PASS — SC-001; pure deterministic functions, hand-verifiable in unit tests |
| Risk First | D1 ATR feeds `calculate_sl_price()` — SL distance always ATR-based | ✅ PASS — FR-006; `get_d1_atr()` is named output to lot_calculator |
| Risk First | Adaptive multipliers widen stop in EXTREME regime (2.0×) | ✅ PASS — FR-007; prevents stop-out on high-volatility moves |
| Risk First | System never returns ATR = 0.0 (division-by-zero risk in lot sizing) | ✅ PASS — D-007; `None` returned on insufficient data; `is_ready()` guard |
| Auditability | Stale cache and refresh failures logged with timestamp + timeframe | ✅ PASS — FR-011; WARNING log on every failure |
| Auditability | Invalid bars logged as WARNING with timestamp | ✅ PASS — FR-012 |
| Quality Gates | Unit test coverage ≥ 80% for `src/analysis/` | ✅ PLANNED — SC-006; 5 unit test files covering all modules |
| Documentation | Docstrings on all public functions explaining rule + why | ✅ ENFORCED — per CLAUDE.md Code Standards |

**Constitution result: PASS — all gates satisfied. No complexity violations.**

---

## Architecture

```
OHLCV Data (spec001 — market_data.py)
         │
         │  list[OHLCVBar]
         ▼
┌────────────────────────────────────┐
│           ATRService               │
│           atr_service.py           │
│                                    │
│  refresh(timeframe, bars)          │
│    │                               │
│    ├─ validate_ohlcv_bars()        │  ← skip invalid bars, log warning
│    ├─ compute_true_range()         │  ← TR = max(H-L, |H-PC|, |L-PC|)
│    ├─ compute_atr(period=14)       │  ← simple avg of last 14 TR values
│    ├─ compute_reference_atr(n=20)  │  ← rolling avg of last 20 ATR values
│    └─ update cache[timeframe]      │  ← ATRCache{reading, is_fresh, ts}
│                                    │
│  get_h1_readings()  ─────────────────────► volatility_filter (spec004)
│  get_d1_atr()       ─────────────────────► lot_calculator (spec003)
│  get_adaptive_multipliers(regime) ───────► lot_calculator (spec003)
│  is_ready(timeframe) ────────────────────► orchestrator guard (spec008)
└────────────────────────────────────┘
```

---

## Project Structure

### Documentation (this feature)

```text
specs/006-atr-calibration/
├── plan.md              ← this file
├── research.md          ← all 10 design decisions resolved
├── data-model.md        ← entities, validation rules, state transitions
├── quickstart.md        ← usage guide, config, test commands
├── contracts/
│   └── atr_service.md   ← full function signatures + error contract
└── tasks.md             ← Phase 2 (/sp.tasks — NOT created by /sp.plan)
```

### Source Code

```text
src/analysis/
├── __init__.py                  — public exports
├── models.py                    — Timeframe, OHLCVBar, VolatilityRegime,
│                                  AdaptiveMultipliers, ATRReading, ATRCache
├── atr_calculator.py            — validate_ohlcv_bars(), compute_true_range(),
│                                  compute_atr()
├── reference_atr.py             — compute_reference_atr()
├── adaptive_multipliers.py      — get_adaptive_multipliers()
└── atr_service.py               — ATRService class (stateful cache orchestrator)

tests/unit/
├── test_atr_models.py
├── test_atr_calculator.py
├── test_reference_atr.py
├── test_adaptive_multipliers.py
└── test_atr_service.py
```

**Structure Decision**: New `src/analysis/` module following identical layout to `src/filters/`, `src/risk/`, `src/execution/` — `models.py` first (no cross-imports), pure functions in dedicated files, single stateful service class as orchestrator.

---

## Key Design Decisions

### D-001: Simple Average ATR (not Wilder's EMA)
Spec explicitly requires arithmetic mean for test determinism. Same 14 bars always produce the same ATR — no warm-up period, no exponential decay. See `research.md` D-001.

### D-002: Reference ATR = 20-Period Rolling Mean of ATR Values
20 H1 ATR values ≈ one trading week. Aligns with the `reference_atr` parameter expected by existing `volatility_filter.py` in spec004. See `research.md` D-002.

### D-003: Bar-Close Cache Invalidation
Orchestrator (spec008) calls `refresh(timeframe, bars)` on each bar close. ATRService does not track time — it receives bars from the caller, exactly as all other modules in this codebase. See `research.md` D-003.

### D-004: Stateful `ATRService` Class
Holds `dict[Timeframe, ATRCache]`. One instance per bot session. Same pattern as `ExecutionEngine`, `RiskManager`, `TradeGate`. See `research.md` D-004.

### D-005: No MT5 Imports in `src/analysis/`
`ATRService.refresh()` accepts pre-fetched `list[OHLCVBar]` from caller. Keeps all 5 analysis files pure and testable without any broker mock. See `research.md` D-005.

### D-006: `Timeframe` Enum Values = MT5 Timeframe Constants
Eliminates a translation table at the broker layer. Same pattern as `Direction` enum in `src/engine/models.py`. See `research.md` D-006.

### D-007: `None` Return on Insufficient Data — Never 0.0
`get_d1_atr()` returns `None` if D1 cache is empty. Prevents division-by-zero in `lot_calculator`. Callers use `is_ready(timeframe)` guard. See `research.md` D-007.

### D-008: Invalid Bar Rejection with WARNING Log
`validate_ohlcv_bars()` filters High < Low or Close ≤ 0. Computation proceeds on valid subset. See `research.md` D-008.

### D-009: Integration Points
H1 `(current_atr, reference_atr)` → `volatility_filter`. D1 `current_atr` → `lot_calculator`. Adaptive multipliers → `lot_calculator`. See `research.md` D-009.

### D-010: `analysis.atr` Config Namespace
New section in `config.yaml` — separate from existing `filters`, `risk`, `execution`. See `research.md` D-010.

---

## Module Breakdown

### `src/analysis/models.py`
- `Timeframe` enum: M5=5, H1=16385, H4=16388, D1=16408
- `OHLCVBar` frozen dataclass: open, high, low, close, volume, timestamp
- `VolatilityRegime` enum: LOW, NORMAL, EXTREME
- `AdaptiveMultipliers` frozen dataclass: sl_multiplier, tp_multiplier, regime
- `ATRReading` dataclass: timeframe, current_atr (Optional), reference_atr (Optional), ratio (Optional), bar_count, timestamp
- `ATRCache` dataclass: reading, is_fresh, last_refreshed
- Zero broker imports.

### `src/analysis/atr_calculator.py`
- `validate_ohlcv_bars(bars)` → `list[OHLCVBar]` — filters invalid bars, logs WARNING per rejection
- `compute_true_range(bars)` → `list[float]` — TR for each bar pair; len = len(bars) - 1
- `compute_atr(bars, period=14)` → `Optional[float]` — None if < period+1 valid bars

### `src/analysis/reference_atr.py`
- `compute_reference_atr(atr_history, period=20)` → `Optional[float]` — None if len(history) < period

### `src/analysis/adaptive_multipliers.py`
- `get_adaptive_multipliers(regime, config)` → `AdaptiveMultipliers` — reads from `config['analysis']['atr']['adaptive_multipliers']`

### `src/analysis/atr_service.py`
- `ATRService.__init__(config)` — empty cache for all 4 timeframes
- `ATRService.refresh(timeframe, bars)` → `ATRReading` — validates, computes, updates cache, never raises
- `ATRService.get_atr(timeframe)` → `Optional[float]`
- `ATRService.get_h1_readings()` → `tuple[Optional[float], Optional[float]]`
- `ATRService.get_d1_atr()` → `Optional[float]`
- `ATRService.get_adaptive_multipliers(regime)` → `AdaptiveMultipliers`
- `ATRService.is_ready(timeframe)` → `bool`
- `ATRService.mark_stale(timeframe)` → `None`

### `src/analysis/__init__.py`
Exports all public symbols from all 5 modules.

---

## Config Updates (`config.yaml`)

```yaml
analysis:
  atr:
    period: 14
    reference_period: 20
    adaptive_multipliers:
      sl:
        LOW: 1.0
        NORMAL: 1.5
        EXTREME: 2.0
      tp:
        LOW: 2.0
        NORMAL: 3.0
        EXTREME: 4.0
```

---

## Test Strategy

### Unit Tests (no MT5 — pure functions)

| File | Requirements Covered |
|------|---------------------|
| `test_atr_models.py` | Entity instantiation, VolatilityRegime members, Timeframe values, ATRReading invariants |
| `test_atr_calculator.py` | TR formula correctness; simple avg ATR ±0.1% (SC-001); None on < 14 bars (SC-005); invalid bar rejection (FR-012) |
| `test_reference_atr.py` | Rolling avg correctness (SC-007 determinism); None on < 20 values; edge case: all same values |
| `test_adaptive_multipliers.py` | All 3 regimes return correct multipliers (SC-004); missing config raises KeyError |
| `test_atr_service.py` | Cache miss on startup; refresh updates cache; stale-fallback on refresh failure (FR-011); mark_stale; is_ready; get_h1_readings / get_d1_atr return None when empty (D-007) |

### Coverage Target
≥ 80% for all `src/analysis/` modules (SC-006)

---

## Phased Delivery

```
Phase 1: models.py + test_atr_models.py
         — All dataclasses and enums; no deps; required by all other phases

Phase 2: atr_calculator.py + test_atr_calculator.py
         — TR formula, ATR computation, bar validation; pure functions

Phase 3: reference_atr.py + test_reference_atr.py
         — Rolling reference ATR; pure function

Phase 4: adaptive_multipliers.py + test_adaptive_multipliers.py
         — Regime → multiplier lookup; config-driven

Phase 5: atr_service.py + test_atr_service.py
         — Stateful cache, refresh, stale fallback, all integration points

Phase 6: __init__.py + config.yaml update + coverage check
         — Wire up public exports; add analysis.atr config section
```

---

## Risks & Follow-ups

- **Startup latency**: On first boot, `refresh()` must process 39+ bars per timeframe (14 ATR + 20 reference + 5 buffer). Four timeframes = 4 MT5 OHLCV fetches. Orchestrator (spec008) should call refresh for all timeframes at startup before entering the main tick loop.
- **Reference ATR history across sessions**: Cache is in-memory only. On restart, the 20-bar ATR history must be recomputed from historical OHLCV data. This is correct behaviour per the Assumptions section — no persistence needed.
- **Timeframe value collision**: `Timeframe.M5.value = 5` is the MT5 constant for TIMEFRAME_M5. Verify this against the installed MetaTrader5 Python package constants when connecting to live broker (MT5 constants are documented but verify `mt5.TIMEFRAME_M5 == 5` in integration test).
