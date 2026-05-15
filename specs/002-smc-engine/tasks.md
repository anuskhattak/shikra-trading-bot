# Tasks: SMC Signal Detection Engine

**Input**: Design documents from `specs/002-smc-engine/`
**Branch**: `002-smc-engine`
**Date**: 2026-05-14
**Prerequisites**: plan.md ✅ | spec.md ✅ | data-model.md ✅ | contracts/smc_engine.md ✅ | quickstart.md ✅

**Tests**: Included — SC-008 requires ≥80% unit test coverage for all 5 detection functions.

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies between them)
- **[Story]**: User story this task belongs to (US1–US5)
- All paths are relative to repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create directory structure, add dependencies, and configure the engine section in config.yaml.

- [x] T001 Create `src/engine/` directory structure (empty `__init__.py` placeholder) and `tests/unit/conftest.py` with `make_ohlcv(n, seed=42)` fixture factory returning valid OHLCV DataFrames with columns `[time, open, high, low, close, tick_volume]` (shared by all 7 test files — U1)
- [x] T002 Add `pandas>=2.0`, `numpy>=1.24`, `loguru`, `pyyaml` to `requirements.txt`
- [x] T003 [P] Create `logs/` directory and add `logs/false_signals.json` to `.gitignore`
- [x] T004 [P] Create or update `config.yaml` at repo root — add `smc_engine:` section per data-model.md Config Schema (fractal_n, lookback_window, tolerance, threshold, weights, min_candles) — F1: file may not exist yet

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: All enums and dataclasses that every detector depends on. No detector can be built until models.py is complete.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T005 Implement all enums in `src/engine/models.py`: `Bias`, `Direction`, `SignalType`, `FVGStatus`, `OBStatus`, `SweepType`
- [x] T006 Implement all dataclasses in `src/engine/models.py`: `SwingPoint`, `FVGZone`, `OrderBlock`, `LiquiditySweep`, `EntrySignal` (with all fields from data-model.md)
- [x] T007 Create `src/engine/__init__.py` — export `EntrySignal`, `Bias`, `Direction` from `models.py` directly; add `generate_signal` stub that raises `NotImplementedError("implemented in Phase 7")`; callers MUST import from `src.engine.models` until T022 replaces the stub (F2)

**Checkpoint**: `from src.engine.models import EntrySignal, Bias, Direction` must import without error before proceeding.

---

## Phase 3: User Story 1 — Trend Direction via BOS / CHoCH (Priority: P1) 🎯 MVP

**Goal**: Detect fractal swing points and identify Break of Structure (BOS) or Change of Character (CHoCH) from H1 candle data. All downstream detectors and the scorer depend on this output.

**Independent Test**: Feed 60-candle DataFrame with a clear swing-high break → engine returns `BOS_BULLISH`. Feed established-bullish + swing-low break → returns `CHoCH_BEARISH`. Ranging market → `SignalType.NONE`.

### Tests for User Story 1 ⚠️ Write FIRST — must FAIL before implementation

- [x] T008 [P] [US1] Write failing unit tests for fractal swing detection (confirmed vs unconfirmed pivots, edge cases: <50 candles, flat market) in `tests/unit/test_engine_swing.py`
- [x] T009 [P] [US1] Write failing unit tests for BOS/CHoCH detection (wick-only move rejected, close-through accepted, conflict resolution, ranging market = NONE) in `tests/unit/test_engine_bos_choch.py`

### Implementation for User Story 1

- [x] T010 [US1] Implement `detect_swing_points(df, fractal_n, lookback) -> list[SwingPoint]` in `src/engine/swing.py` — fractal rule: N candles on each side with strictly lower highs / higher lows; unconfirmed pivots excluded; last fractal_n rows always excluded; **inline comments MUST explain the fractal pivot rule per NFR-001** (FR-001)
- [x] T011 [US1] Implement `detect_structure_break(df, swing_points) -> tuple[SignalType, float | None]` in `src/engine/bos_choch.py` — use `df['close']` only (never wick), CHoCH requires established trend from last confirmed BOS direction, return `(NONE, None)` for ranging market; **inline comments MUST explain BOS and CHoCH rules and why wicks are excluded per NFR-001** (FR-002, FR-003, FR-004, D-006)

**Checkpoint**: Run `pytest tests/unit/test_engine_swing.py tests/unit/test_engine_bos_choch.py` — all tests must pass.

---

## Phase 4: User Story 2 — Fair Value Gap as Entry Zone (Priority: P2)

**Goal**: Scan candle history for FVG imbalances, determine fill status using candle-close rule, and return ordered list of active zones.

**Independent Test**: 3-candle sequence where `candle[N-2].high < candle[N].low` → bullish FVG detected with correct `top`, `bottom`, `midpoint`, `status=UNFILLED`. Subsequent close inside zone → status updates to `FILLED`.

### Tests for User Story 2 ⚠️ Write FIRST — must FAIL before implementation

- [x] T012 [P] [US2] Write failing unit tests for FVG detection (bullish FVG, bearish FVG, fill detection by close not wick, multiple stacked FVGs, direction filter, empty result when no gap) in `tests/unit/test_engine_fvg.py`

### Implementation for User Story 2

- [x] T013 [US2] Implement `detect_fvg_zones(df, direction_filter) -> list[FVGZone]` in `src/engine/fvg.py` — scan all 3-candle windows; compute top/bottom/midpoint; apply fill check using close-only rule; return newest-first; honour `direction_filter`; **inline comments MUST explain the 3-candle gap rule and why wick fills are rejected per NFR-001** (FR-005, FR-006, FR-007, FR-008)

**Checkpoint**: Run `pytest tests/unit/test_engine_fvg.py` — all tests must pass.

---

## Phase 5: User Story 3 — Order Block for Precise Entry (Priority: P3)

**Goal**: Identify the last opposing candle before a BOS as an Order Block. Track status through ACTIVE → TESTED (wick) → INVALIDATED (close-through).

**Independent Test**: Last bearish candle before bullish BOS → Bullish OB with `top=max(open,close)`, `bottom=min(open,close)`, `status=ACTIVE`. Wick entry → TESTED. Close-through → INVALIDATED.

### Tests for User Story 3 ⚠️ Write FIRST — must FAIL before implementation

- [x] T014 [P] [US3] Write failing unit tests for Order Block detection (bullish OB, bearish OB, OB body boundaries use open/close not wicks, ACTIVE→TESTED→INVALIDATED transitions, fast-move ACTIVE→INVALIDATED, no OB when no BOS) in `tests/unit/test_engine_order_block.py`

### Implementation for User Story 3

- [x] T015 [US3] Implement `detect_order_blocks(df, bos_type, bos_candle_index) -> list[OrderBlock]` in `src/engine/order_block.py` — identify last opposing candle before BOS candle; apply state transitions: TESTED on wick entry (`candle.low <= ob.top`), INVALIDATED on close-through; use body boundaries only; **inline comments MUST explain the OB origin rule, TESTED vs INVALIDATED distinction (D-007), and why body not wick is used per NFR-001** (FR-009, FR-010, FR-011, FR-012, D-007)

**Checkpoint**: Run `pytest tests/unit/test_engine_order_block.py` — all tests must pass.

---

## Phase 6: User Story 4 — Liquidity Sweep as Reversal Confirmation (Priority: P4)

**Goal**: Detect stop-hunt events where price wicks beyond equal highs/lows and closes back within the same candle.

**Independent Test**: Two candle highs within 5 pips followed by wick above + close below → `LIQUIDITY_SWEEP_HIGH` recorded with correct `sweep_level` and `close_price`. No equal levels → empty list.

### Tests for User Story 4 ⚠️ Write FIRST — must FAIL before implementation

- [x] T016 [P] [US4] Write failing unit tests for Liquidity Sweep (sweep high, sweep low, within-tolerance equal levels, no sweep when close doesn't return inside, configurable pip_tolerance, empty result when no equal levels) in `tests/unit/test_engine_liquidity_sweep.py`

### Implementation for User Story 4

- [x] T017 [US4] Implement `detect_liquidity_sweeps(df, pip_tolerance) -> list[LiquiditySweep]` in `src/engine/liquidity_sweep.py` — cluster equal highs/lows within `pip_tolerance` ($0.50 default = 5 pips for XAUUSD); detect HIGH sweep: wick above cluster + close below; detect LOW sweep: wick below + close above; record `sweep_level` and `close_price`; return newest-first; **inline comments MUST explain the stop-hunt mechanics and same-candle close rule per NFR-001** (FR-013, FR-014, FR-015, FR-016)

**Checkpoint**: Run `pytest tests/unit/test_engine_liquidity_sweep.py` — all tests must pass.


---

## Phase 7: User Story 5 — Scored Entry Signal (Priority: P1)

**Goal**: Combine all detected components into a single `EntrySignal` with additive confidence score. Discard low-confidence signals. Log every discard to `logs/false_signals.json`. Expose single public entry point `generate_signal()`.

**Independent Test**: BOS+FVG+OB all bullish → `confidence ≥ 0.70`, `direction=LONG`. BOS only → `confidence=0.40 < 0.65 threshold` → discarded, entry written to `false_signals.json`. Every call returns valid `EntrySignal` (never `None`).

### Tests for User Story 5 ⚠️ Write FIRST — must FAIL before implementation

- [x] T018 [P] [US5] Write failing unit tests for scorer (full confluence = confidence ≥ 0.70, BOS-only rejection, OB entry_zone priority over FVG fallback, FVG fallback when no OB, sweep bonus, htf_bias filter rejects misaligned signals, NONE signal invariants: entry_zone=(0,0)) in `tests/unit/test_engine_scorer.py`
- [x] T019 [P] [US5] Write failing integration tests for full pipeline (BOS+FVG+OB→EntrySignal, <50 candles→NONE, never raises on valid DataFrame, deterministic output for identical input) in `tests/integration/test_engine_pipeline.py` — multi-module scope warrants `integration/` not `unit/` (F3)

### Implementation for User Story 5

- [x] T020 [US5] Implement `score_and_assemble(signal_type, fvg_zones, order_blocks, sweeps, weights, threshold, htf_bias) -> EntrySignal` in `src/engine/scorer.py` — additive weighted sum (D-005); OB body as entry_zone primary / FVG fallback (D-004, FR-017); discard below threshold with `false_signals.json` append; populate `reason` and `components` list; clip confidence to [0.0, 1.0] (FR-017 to FR-024)
- [x] T021 [US5] Implement `generate_signal(df, htf_bias, config) -> EntrySignal` in `src/engine/smc_engine.py` — load config (file default → caller override); guard: return NONE if `len(df) < min_candles`; call swing → bos_choch → fvg → order_block → liquidity_sweep → scorer in sequence; wrap all sub-calls in try/except returning NONE signal on unexpected error; no MT5 import (FR-021, FR-022, NFR-002, NFR-003, SC-005)
- [x] T022 [US5] Update `src/engine/__init__.py` to export `generate_signal`, `EntrySignal`, `Bias` from real modules

**Checkpoint**: Run `pytest tests/unit/test_engine_scorer.py tests/integration/test_engine_pipeline.py` — all tests must pass. Verify `logs/false_signals.json` entries appear for rejected signals.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Coverage validation, performance benchmark, and quickstart smoke test.

- [x] T023 [P] Run `pytest --cov=src/engine --cov-report=term-missing` and confirm coverage ≥ 80% for all five detection modules (SC-008)
- [x] T024 [P] Benchmark `generate_signal()` with 200-row synthetic DataFrame — must complete in < 100ms; add timing assertion to `tests/integration/test_engine_pipeline.py` (SC-005, SC-006)
- [x] T025 Run quickstart.md Step 4 (synthetic data smoke test) and confirm `signal.direction` is not None, `0.0 ≤ signal.confidence ≤ 1.0`, no exceptions raised

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)          → No dependencies — start immediately
Phase 2 (Foundational)   → Depends on Phase 1 — BLOCKS all user stories
Phase 3 (US1 BOS/CHoCH)  → Depends on Phase 2 — builds on models.py
Phase 4 (US2 FVG)        → Depends on Phase 2 — parallel with US1 after Phase 2
Phase 5 (US3 OB)         → Depends on Phase 2 — parallel with US1/US2 after Phase 2
Phase 6 (US4 LS)         → Depends on Phase 2 — parallel with others after Phase 2
Phase 7 (US5 Scorer)     → Depends on Phases 3+4+5+6 — integrates all detectors
Phase 8 (Polish)         → Depends on Phase 7
```

### User Story Dependencies

| Story | Depends On | Can Parallelise With |
|-------|-----------|----------------------|
| US1 BOS/CHoCH (P1) | Phase 2 complete | US2, US3, US4 |
| US2 FVG (P2) | Phase 2 complete | US1, US3, US4 |
| US3 Order Block (P3) | Phase 2 complete | US1, US2, US4 |
| US4 Liquidity Sweep (P4) | Phase 2 complete | US1, US2, US3 |
| US5 Scorer (P1) | US1+US2+US3+US4 all complete | — |

**Note**: US1 and US5 are both P1. US1 must be completed first because US5 consumes its output (`SignalType`).

### Within Each User Story

1. Write tests FIRST (they must fail before implementation)
2. Implement until tests pass
3. Run story checkpoint before moving on

---

## Parallel Example: Phases 3–6

After Phase 2 is complete, all four detectors can be built simultaneously:

```
Stream A: T008 → T009 → T010 → T011  (US1: swing + BOS/CHoCH)
Stream B: T012 → T013                 (US2: FVG)
Stream C: T014 → T015                 (US3: Order Block)
Stream D: T016 → T017                 (US4: Liquidity Sweep)
                                       ↓ all merge at US5
                    T018 → T019 → T020 → T021 → T022  (US5: Scorer + Orchestrator)
```

---

## Implementation Strategy

### MVP First (US1 + US5 Only — minimum viable signal)

1. Complete Phase 1 (Setup)
2. Complete Phase 2 (Foundational — models)
3. Complete Phase 3 (US1 — BOS/CHoCH detection)
4. Complete Phase 7 partial: scorer with BOS-only input (confidence = 0.40 always, below threshold)
5. **STOP and VALIDATE**: BOS fires; scorer rejects correctly; false_signals.json entries appear
6. Add US2 (FVG) → scorer reaches 0.70 threshold → first accepted signals

### Incremental Delivery

```
After Phase 3 (US1):  Trend detection works — BOS/CHoCH tested in isolation
After Phase 4 (US2):  Entry zone identified — FVG detection works
After Phase 5 (US3):  Precise entry level — OB detection works
After Phase 6 (US4):  Sweep confirmation — LS detection works
After Phase 7 (US5):  Full scored signal — system end-to-end complete
After Phase 8:        Coverage ≥ 80%, perf validated, quickstart runs clean
```

---

## Task Summary

| Phase | Tasks | Count |
|-------|-------|-------|
| Phase 1 — Setup | T001–T004 | 4 |
| Phase 2 — Foundational | T005–T007 | 3 |
| Phase 3 — US1 BOS/CHoCH | T008–T011 | 4 |
| Phase 4 — US2 FVG | T012–T013 | 2 |
| Phase 5 — US3 Order Block | T014–T015 | 2 |
| Phase 6 — US4 Liquidity Sweep | T016–T017 | 2 |
| Phase 7 — US5 Scorer | T018–T022 | 5 |
| Phase 8 — Polish | T023–T025 | 3 |
| **Total** | | **25** |

**Parallel opportunities**: T002/T003/T004 (Phase 1), T005/T006 (Phase 2), US1+US2+US3+US4 (Phases 3–6), T018/T019 (US5 tests)
