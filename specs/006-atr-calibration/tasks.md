# Tasks: ATR Calibration Module

**Input**: Design documents from `/specs/006-atr-calibration/`  
**Branch**: `006-atr-calibration`  
**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/ ✅

**Tests**: Included — spec SC-006 requires ≥ 80% unit test coverage for `src/analysis/`

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared state)
- **[US#]**: Maps to user story in spec.md

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create `src/analysis/` directory structure and test scaffolding.

- [x] T001 Create `src/analysis/` directory with empty `__init__.py` placeholder
- [x] T002 Create `tests/unit/` directory for analysis unit tests (if not already present)
- [x] T003 [P] Add `analysis.atr` config section to `config.yaml` with all defaults (period: 14, reference_period: 20, adaptive_multipliers sl/tp per regime)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: All shared data models used across every user story. Must be complete before any US phase.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T004 Implement `Timeframe` enum (M5=5, H1=16385, H4=16388, D1=16408) in `src/analysis/models.py`
- [x] T005 Implement `OHLCVBar` frozen dataclass (open, high, low, close, volume, timestamp) in `src/analysis/models.py`
- [x] T006 Implement `VolatilityRegime` enum (LOW, NORMAL, EXTREME) in `src/analysis/models.py`
- [x] T007 Implement `AdaptiveMultipliers` frozen dataclass (sl_multiplier, tp_multiplier, regime) in `src/analysis/models.py`
- [x] T008 Implement `ATRReading` dataclass (timeframe, current_atr Optional[float], reference_atr Optional[float], ratio Optional[float], bar_count: int, timestamp) in `src/analysis/models.py`
- [x] T009 Implement `ATRCache` dataclass (reading, is_fresh, last_refreshed) in `src/analysis/models.py`
- [x] T010 Write `tests/unit/test_atr_models.py` — verify all entity instantiation, Timeframe.H1.value == 16385, ATRReading accepts None for optional fields, VolatilityRegime members

**Checkpoint**: Foundation ready — all shared models available; user story phases can now proceed.

---

## Phase 3: User Story 1 — ATR Values Available for Signal Pipeline (Priority: P1) 🎯 MVP

**Goal**: Compute True Range and ATR for any timeframe from OHLCV bars; serve fresh/cached values.

**Independent Test**: `pytest tests/unit/test_atr_calculator.py -v` passes; ATR for 14+ bars within ±0.1% of hand-calculated reference.

- [x] T011 [US1] Implement `validate_ohlcv_bars(bars: list[OHLCVBar]) -> list[OHLCVBar]` in `src/analysis/atr_calculator.py` — filter bars where high < low or close ≤ 0; log WARNING per rejected bar with timestamp
- [x] T012 [US1] Implement `compute_true_range(bars: list[OHLCVBar]) -> list[float]` in `src/analysis/atr_calculator.py` — TR = max(H-L, |H-PrevClose|, |L-PrevClose|); raises ValueError if < 2 bars
- [x] T013 [US1] Implement `compute_atr(bars: list[OHLCVBar], period: int = 14) -> Optional[float]` in `src/analysis/atr_calculator.py` — simple arithmetic mean of last `period` TR values; return None if insufficient data
- [x] T014 [US1] Write `tests/unit/test_atr_calculator.py` covering: TR formula correctness (hand-calculated 3-bar example), ATR ±0.1% accuracy (14-bar XAUUSD-like data), None returned when < 15 bars, invalid bar filtering (high < low skipped), all-invalid-bars returns None, empty list raises ValueError

**Checkpoint**: US1 complete — `compute_atr()` fully functional and tested independently.

---

## Phase 4: User Story 2 — Reference ATR for Volatility Regime Classification (Priority: P1)

**Goal**: Compute a stable reference ATR (20-period rolling average) as baseline for volatility ratio.

**Independent Test**: `pytest tests/unit/test_reference_atr.py -v` passes; same input always returns same output (SC-007 determinism).

- [x] T015 [US2] Implement `compute_reference_atr(atr_history: list[float], period: int = 20) -> Optional[float]` in `src/analysis/reference_atr.py` — arithmetic mean of last `period` values; return None if len < period; oldest-first input order
- [x] T016 [US2] Write `tests/unit/test_reference_atr.py` covering: correct rolling avg from 20 values, None when < 20 values, determinism (same input → same output SC-007), edge case all-same-values, reference equals current → ratio = 1.0 (NORMAL), reference × 2 = current → ratio = 2.0 (EXTREME boundary)

**Checkpoint**: US2 complete — `compute_reference_atr()` functional; volatility_filter can now receive both current and reference ATR.

---

## Phase 5: User Story 3 — Adaptive SL/TP Multipliers by Volatility Regime (Priority: P2)

**Goal**: Return correct SL and TP multipliers for any VolatilityRegime from config.

**Independent Test**: `pytest tests/unit/test_adaptive_multipliers.py -v` passes; all three regimes return expected multiplier values.

- [x] T017 [US3] Implement `get_adaptive_multipliers(regime: VolatilityRegime, config: dict) -> AdaptiveMultipliers` in `src/analysis/adaptive_multipliers.py` — read from `config['analysis']['atr']['adaptive_multipliers']`; raises KeyError with descriptive message if section missing
- [x] T018 [US3] Write `tests/unit/test_adaptive_multipliers.py` covering: LOW regime returns sl=1.0, tp=2.0; NORMAL returns sl=1.5, tp=3.0; EXTREME returns sl=2.0, tp=4.0; missing config key raises KeyError; custom config values respected; AdaptiveMultipliers.regime field matches input regime

**Checkpoint**: US3 complete — adaptive multipliers functional; lot_calculator can now receive regime-adjusted SL/TP factors.

---

## Phase 6: User Story 4 — ATR Cache with Bar-Close Refresh (Priority: P2)

**Goal**: Stateful `ATRService` that caches ATR per timeframe, refreshes on bar close, and handles stale/failure gracefully.

**Independent Test**: `pytest tests/unit/test_atr_service.py -v` passes; 100% of intra-bar requests served from cache (SC-002); stale fallback on refresh failure (FR-011).

- [x] T019 [US4] Implement `ATRService.__init__(config)` in `src/analysis/atr_service.py` — initialise empty `dict[Timeframe, ATRCache]` for all 4 timeframes; validate `config['analysis']['atr']` section exists
- [x] T020 [US4] Implement `ATRService.refresh(timeframe, bars) -> ATRReading` in `src/analysis/atr_service.py` — validates bars, computes current_atr + reference_atr, updates cache with is_fresh=True; on failure preserves last cached value, sets is_fresh=False, logs WARNING; never raises
- [x] T021 [US4] Implement `ATRService.get_atr()`, `get_h1_readings()`, `get_d1_atr()`, `is_ready()`, `mark_stale()` in `src/analysis/atr_service.py` — all return None/False on empty cache; no recomputation between refreshes
- [x] T022 [US4] Implement `ATRService.get_adaptive_multipliers(regime)` in `src/analysis/atr_service.py` — delegates to `adaptive_multipliers.get_adaptive_multipliers()`
- [x] T023 [US4] Write `tests/unit/test_atr_service.py` covering: empty cache returns None for all getters, refresh populates cache and sets is_fresh=True, mark_stale sets is_fresh=False, repeated get_atr() calls return identical cached value (no recomputation), refresh failure preserves last value + logs WARNING, is_ready() returns False on empty and True after refresh, get_h1_readings() returns tuple[None, None] on empty, get_d1_atr() returns None on empty, full round-trip (refresh H1 → get_h1_readings → classify regime → get_adaptive_multipliers)

**Checkpoint**: US4 complete — full ATRService functional; all 4 user stories independently working.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Wire up public exports, verify coverage, confirm integration points work end-to-end.

- [x] T024 Update `src/analysis/__init__.py` with all public exports: Timeframe, VolatilityRegime, OHLCVBar, AdaptiveMultipliers, ATRReading, ATRCache, ATRService, compute_atr, compute_true_range, validate_ohlcv_bars, compute_reference_atr, get_adaptive_multipliers
- [x] T025 [P] Run coverage check: `pytest tests/unit/ -k "atr" --cov=src/analysis --cov-report=term-missing` — confirm ≥ 80% coverage across all `src/analysis/` files (SC-006). Note: SC-003 refresh timing (< 1 second) is a manual verification item during spec008 integration test — not measured in unit tests.
- [x] T026 [P] Verify `volatility_filter.check_volatility()` integration: write a smoke test in `tests/unit/test_atr_service.py` confirming `get_h1_readings()` output can be passed directly into `check_volatility(current_atr, reference_atr, config)` without type errors
- [x] T027 [P] Verify `lot_calculator` integration: confirm `get_d1_atr()` output passes to `calculate_sl_price(entry, direction, d1_atr)` and `get_adaptive_multipliers()` output's `sl_multiplier` passes to `calculate_sl_price(sl_atr_multiplier=...)` without type errors

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — **BLOCKS all user story phases**
- **Phase 3 (US1)**: Depends on Phase 2 only — no inter-story dependencies
- **Phase 4 (US2)**: Depends on Phase 2 only — no inter-story dependencies
- **Phase 5 (US3)**: Depends on Phase 2 only — no inter-story dependencies
- **Phase 6 (US4)**: Depends on Phases 3, 4, and 5 (ATRService calls atr_calculator, reference_atr, adaptive_multipliers)
- **Phase 7 (Polish)**: Depends on all phases complete

### User Story Dependencies

- **US1 (P1)**: After Phase 2 — independent
- **US2 (P1)**: After Phase 2 — independent of US1
- **US3 (P2)**: After Phase 2 — independent of US1 and US2
- **US4 (P2)**: After US1 + US2 + US3 complete (service orchestrates all three)

### Within Each Phase

- Foundational: T005–T009 fully parallel (different fields in same file — write sequentially within models.py)
- US1: T011 → T012 → T013 sequential (each builds on prior); T014 tests can be written alongside
- US2: T015 then T016 (implementation before tests)
- US3: T017 then T018
- US4: T019 → T020 → T021 → T022 sequential; T023 after T022

### Parallel Opportunities

- T003 (config.yaml) can run in parallel with T004-T009 (models)
- T011-T013 (US1 atr_calculator) can run in parallel with T015 (US2 reference_atr) after Phase 2
- T017 (US3 adaptive_multipliers) can run in parallel with T015 and T011-T013 after Phase 2
- T025, T026, T027 all parallel in Phase 7

---

## Parallel Execution Example: Phases 3-5

```bash
# After Phase 2 completes, these can run simultaneously:

# Stream A — US1
Task T011: validate_ohlcv_bars() in src/analysis/atr_calculator.py
Task T012: compute_true_range() in src/analysis/atr_calculator.py
Task T013: compute_atr() in src/analysis/atr_calculator.py
Task T014: tests/unit/test_atr_calculator.py

# Stream B — US2 (parallel with Stream A)
Task T015: compute_reference_atr() in src/analysis/reference_atr.py
Task T016: tests/unit/test_reference_atr.py

# Stream C — US3 (parallel with Streams A & B)
Task T017: get_adaptive_multipliers() in src/analysis/adaptive_multipliers.py
Task T018: tests/unit/test_adaptive_multipliers.py
```

---

## Implementation Strategy

### MVP (User Stories 1 + 2 — both P1)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (models.py + test_atr_models.py)
3. Complete Phase 3: US1 — compute_atr() working and tested
4. Complete Phase 4: US2 — compute_reference_atr() working and tested
5. **STOP and VALIDATE**: `get_h1_readings()` can now feed `volatility_filter.check_volatility()`
6. Deploy/demo if ready

### Full Delivery

1. Setup + Foundational → models ready
2. US1 + US2 + US3 in parallel (independent) → all pure functions ready
3. US4 → ATRService wires everything together
4. Polish → coverage gate, integration smoke tests

---

## Notes

- T005–T009 are all in `models.py` — write sequentially in one file (same file, no true parallelism); [P] markers removed to avoid confusion
- `ATRService` (US4) is the only phase that depends on all prior phases — it's the integration layer
- All `src/analysis/` files have zero MT5 imports — no broker mock needed in any unit test
- `Timeframe.value` constants (5, 16385, 16388, 16408) must match MT5 Python package — verify in integration test when spec008 (orchestrator) is implemented
- Total tasks: **27** (T001–T027)
