# Tasks: H4 Bias Engine

**Input**: Design documents from `/specs/007-h4-bias-engine/`  
**Branch**: `007-h4-bias-engine`  
**Date**: 2026-06-12  
**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/ ✅

**Total Tasks**: 36  
**Tests**: Included per project quality gate (≥ 80% unit test coverage required by CLAUDE.md)

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[Story]**: Maps to user story from spec.md (US1–US5)

---

## Phase 1: Setup (Config & Prerequisites)

**Purpose**: Extend configuration schema so all subsequent phases have the required keys.

- [x] T001 Add `analysis.h4_bias` config block (lookback_bars: 20, fractal_n: 2, bullish_strength_threshold: 0.60, bearish_strength_threshold: 0.60) to `config.yaml`
- [x] T002 Add `h4_alignment: 0.20` and `mtf_boost: 1.30` under `smc_engine.weights` section in `config.yaml`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core model changes that every user story phase depends on. MUST complete before Phase 3+.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T003 Add `RANGING = "RANGING"` value to `Bias` enum in `src/engine/models.py`
- [x] T004 Add `h4_bias: Bias` field (default `Bias.NEUTRAL`) at the end of `EntrySignal` dataclass in `src/engine/models.py`
- [x] T005 Add `h4_bias_strength: float` field (default `0.0`) at the end of `EntrySignal` dataclass in `src/engine/models.py`
- [x] T006 Add `h4_bias_result: Optional[H4BiasResult]` field (default `None`) to `PipelineContext` dataclass in `src/orchestrator/models.py` (import from `src.analysis.h4_bias`)

**Checkpoint**: All downstream modules can now reference `Bias.RANGING`, `EntrySignal.h4_bias`, and `PipelineContext.h4_bias_result` without import errors.

---

## Phase 3: User Stories 1 & 2 — H4 Bias Detection + Ranging Block (Priority: P1) 🎯 MVP

**Goal**: Create `H4BiasService` that classifies H4 structure as BULLISH/BEARISH/RANGING, and block all trades when RANGING.

**Independent Test**: Instantiate `H4BiasService(config)`, call `refresh(h4_bars)` with trending bars → verify BULLISH/BEARISH returned. Call `score_and_assemble()` with `htf_bias=Bias.RANGING` → verify NONE signal with `H4_RANGING` reason.

### Implementation for User Stories 1 & 2

- [x] T007 [US1] Create `H4BiasResult` frozen dataclass (fields: bias, strength, swing_count, timestamp) in `src/analysis/h4_bias.py` (new file)
- [x] T008 [US1] Implement `classify_bias(swing_points, bullish_threshold, bearish_threshold) -> tuple[Bias, float]` in `src/analysis/h4_bias.py` — separates HIGHs/LOWs, counts HH/HL vs LH/LL pairs, returns strength score
- [x] T009 [US1] Implement `H4BiasService.__init__(config)` in `src/analysis/h4_bias.py` — reads `config['analysis']['h4_bias']`, raises `KeyError` if missing, initialises empty cache
- [x] T010 [US1] Implement `H4BiasService.refresh(h4_bars) -> H4BiasResult` in `src/analysis/h4_bias.py` — converts bars to DataFrame, calls `detect_swing_points()` from `src/engine/swing.py`, calls `classify_bias()`, stores in cache, never raises
- [x] T011 [US1] Implement `H4BiasService.get_bias() -> H4BiasResult` and `H4BiasService.is_ready() -> bool` in `src/analysis/h4_bias.py` — returns RANGING/0.0 result before first successful refresh
- [x] T012 [P] [US1] Export `H4BiasService` and `H4BiasResult` from `src/analysis/__init__.py`
- [x] T013 [US2] Add RANGING early-exit block as the FIRST check inside `score_and_assemble()` in `src/engine/scorer.py` — calls `_log_and_discard()` with reason `"H4_RANGING"` and confidence `0.0`

### Tests for User Stories 1 & 2

- [x] T014 [P] [US1] Write `test_bullish_bias_hh_hl`: feed 6 H4 bars making higher-high + higher-low sequence → assert result.bias == BULLISH, result.strength >= 0.6 in `tests/test_h4_bias.py` (new file)
- [x] T015 [P] [US1] Write `test_bearish_bias_lh_ll`: feed 6 H4 bars making lower-high + lower-low sequence → assert result.bias == BEARISH, result.strength >= 0.6 in `tests/test_h4_bias.py`
- [x] T016 [P] [US1] Write `test_ranging_mixed_structure`: feed bars with alternating direction → assert result.bias == RANGING in `tests/test_h4_bias.py`
- [x] T017 [P] [US1] Write `test_cold_start_insufficient_bars`: call `refresh()` with fewer than `lookback_bars` bars → assert RANGING, strength == 0.0, no exception raised in `tests/test_h4_bias.py`
- [x] T018 [P] [US2] Write `test_ranging_blocks_scorer`: call `score_and_assemble()` with any `signal_type` and `htf_bias=Bias.RANGING` → assert `direction == Direction.NONE`, `reason` contains `"H4_RANGING"` in `tests/test_h4_bias.py`

**Checkpoint**: `H4BiasService` is fully functional and independently testable. RANGING blocks signals. Run: `pytest tests/test_h4_bias.py -k "bullish or bearish or ranging or cold_start"` — all 5 tests must pass.

---

## Phase 4: User Stories 3 & 4 — Signal Score Boost + MTF Multiplier + Pipeline Wiring (Priority: P2)

**Goal**: Wire H4 bias into the signal scoring pipeline — add +0.20 alignment boost and ×1.30 MTF multiplier when H4 and H1 align. Recalibrate H4 bias on every H4 bar close.

**Independent Test**: Run `run_pipeline()` with a mock `H4BiasService` returning BULLISH → verify `EntrySignal.h4_bias == Bias.BULLISH` and confidence is boosted above threshold.

### Implementation for User Stories 3 & 4

- [x] T019 [US3] Add `htf_bias_strength: float = 0.0` parameter to `generate_signal()` in `src/engine/smc_engine.py` and pass it through to the `score_and_assemble()` call inside
- [x] T020 [US3] Add `htf_bias_strength: float = 0.0` parameter to `score_and_assemble()` in `src/engine/scorer.py` (after existing `htf_bias` param — default ensures backward compatibility)
- [x] T021 [US3] Add H4 alignment boost block in `score_and_assemble()` in `src/engine/scorer.py`: after component scoring, if bias aligns with direction add `weights.get("h4_alignment", 0.20)` to confidence and append `"H4_ALIGN"` to components
- [x] T022 [US3] Apply MTF multiplier in `score_and_assemble()` in `src/engine/scorer.py`: when H4_ALIGN was added, multiply confidence by `weights.get("mtf_boost", 1.30)`, clip to 1.0
- [x] T023 [US3] Update all `EntrySignal` return sites in `src/engine/scorer.py` (the accepted signal, `_none_signal`, `_log_and_discard`) to embed `h4_bias=htf_bias` and `h4_bias_strength=htf_bias_strength`
- [x] T024 [P] [US4] Add `h4_bias_service: H4BiasService` as a new parameter to `run_pipeline()` in `src/orchestrator/pipeline.py` (update all callers)
- [x] T025 [US4] Add Stage 0 in `run_pipeline()` in `src/orchestrator/pipeline.py`: call `h4_bias_service.refresh(ctx.bars.get(Timeframe.H4, []))`, store result in `ctx.h4_bias_result`
- [x] T026 [US4] Replace `htf_bias=Bias.NEUTRAL` with `htf_bias=ctx.h4_bias_result.bias` and add `htf_bias_strength=ctx.h4_bias_result.strength` in Stage 2 of `run_pipeline()` in `src/orchestrator/pipeline.py`
- [x] T027 [US4] Update `src/backtest/backtest_engine.py` to instantiate `H4BiasService(config)` at startup and pass it to every `run_pipeline()` call

### Tests for User Stories 3 & 4

- [x] T028 [P] [US3] Write `test_alignment_boost_added`: call `score_and_assemble()` with BULLISH bias + LONG signal → assert confidence includes `h4_alignment` weight contribution and `"H4_ALIGN"` in components in `tests/test_h4_bias.py`
- [x] T029 [P] [US3] Write `test_mtf_multiplier_applied`: BULLISH bias + LONG signal with base confidence 0.70 → assert final confidence == min(1.0, 0.70 × 1.30) in `tests/test_h4_bias.py`
- [x] T030 [P] [US4] Write `test_pipeline_wires_h4_service`: create mock `H4BiasService` returning BULLISH, call `run_pipeline()` → assert `ctx.h4_bias_result.bias == Bias.BULLISH` and `ctx.entry_signal.h4_bias == Bias.BULLISH` in `tests/test_h4_bias.py`

**Checkpoint**: Full pipeline uses live H4 bias. Run: `pytest tests/test_h4_bias.py` — all tests pass. Run: `pytest tests/` — no regressions in existing tests.

---

## Phase 5: User Story 5 — Bias State Logging & Auditability (Priority: P3)

**Goal**: Every EntrySignal and trade rejection log contains H4 bias state. Bias state transitions are logged to the audit trail.

**Independent Test**: Run 3 simulated trades → inspect log entries → verify each contains `h4_bias` and `h4_bias_strength` fields with correct values.

### Implementation for User Story 5

- [x] T031 [US5] Add transition logging inside `H4BiasService.refresh()` in `src/analysis/h4_bias.py`: when bias state changes from previous result, call `logger.info("H4 bias transition: {} → {} | strength={:.2f}", prev, new, strength)`
- [x] T032 [P] [US5] Write `test_entry_signal_carries_bias`: generate an accepted signal with BULLISH bias → assert `signal.h4_bias == Bias.BULLISH` and `signal.h4_bias_strength > 0.0` in `tests/test_h4_bias.py`

**Checkpoint**: All 9 unit tests pass. Every signal (accepted or rejected) carries bias fields.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Regression safety, edge case hardening, documentation verification.

- [x] T033 [P] Write `test_no_counter_trend_boost`: BULLISH bias + SHORT signal → assert no `H4_ALIGN` in components, no MTF multiplier, signal discarded as counter-trend in `tests/test_h4_bias.py`
- [x] T034 [P] Write `test_neutral_bias_no_block_no_boost`: NEUTRAL bias + LONG signal with sufficient confidence → assert signal accepted, no H4_ALIGN component in `tests/test_h4_bias.py`
- [x] T035 Run `pytest tests/` from repo root and confirm zero regressions across all existing test suites (spec002–spec006, spec009)
- [x] T036 Verify `src/analysis/__init__.py` exports are complete; run `python -c "from src.analysis.h4_bias import H4BiasService, H4BiasResult; print('OK')"` to confirm importability

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user story phases
- **Phase 3 (US1+US2 P1)**: Depends on Phase 2 — core new file + scorer change
- **Phase 4 (US3+US4 P2)**: Depends on Phase 3 — scorer extension + pipeline wiring
- **Phase 5 (US5 P3)**: Depends on Phase 3 — adds transition logging and audit fields
- **Phase 6 (Polish)**: Depends on Phases 3, 4, 5

### User Story Dependencies

```
Phase 2 (Foundational)
    │
    ├──► Phase 3 (US1+US2 P1) ──► Phase 4 (US3+US4 P2)
    │                                        │
    └──► Phase 5 (US5 P3) ◄──────────────────┘
              │
              ▼
         Phase 6 (Polish)
```

### Within Each Phase

- T007–T011 must be sequential (each builds on the previous function in `h4_bias.py`)
- T019 must complete before T020 (signature must exist before scorer changes)
- T024 must complete before T025–T026 (pipeline param before body changes)
- All `[P]` tasks within a phase have no intra-phase dependencies

---

## Parallel Execution Examples

### Phase 3 — Tests (can all launch together after T013)

```
Task T014: test_bullish_bias_hh_hl
Task T015: test_bearish_bias_lh_ll
Task T016: test_ranging_mixed_structure
Task T017: test_cold_start_insufficient_bars
Task T018: test_ranging_blocks_scorer
```

### Phase 4 — Tests (can all launch together after T023)

```
Task T028: test_alignment_boost_added
Task T029: test_mtf_multiplier_applied
Task T030: test_pipeline_wires_h4_service
```

### Phase 6 — Polish tests (can all launch together)

```
Task T033: test_no_counter_trend_boost
Task T034: test_neutral_bias_no_block_no_boost
```

---

## Implementation Strategy

### MVP (User Stories 1 & 2 Only — Phase 1–3)

1. Complete Phase 1: Config update (T001–T002)
2. Complete Phase 2: Model changes (T003–T006)
3. Complete Phase 3: H4BiasService + RANGING block (T007–T018)
4. **STOP and VALIDATE**: `pytest tests/test_h4_bias.py` — all 5 tests pass
5. Result: Working bias detector, RANGING filter active, full audit trail for US1/US2

### Incremental Delivery

1. Phase 1–3 → US1+US2 complete (MVP)
2. Add Phase 4 → US3+US4 complete (alignment boost + pipeline wired)
3. Add Phase 5 → US5 complete (full audit logging)
4. Phase 6 → Regression clean, ready for `/sp.implement` on spec008

---

## Summary

| Phase | Tasks | Stories | Parallelizable |
|-------|-------|---------|----------------|
| 1 Setup | T001–T002 | — | 0 |
| 2 Foundational | T003–T006 | — | 0 (sequential model edits) |
| 3 US1+US2 (P1) | T007–T018 | US1, US2 | 5 tests |
| 4 US3+US4 (P2) | T019–T030 | US3, US4 | 3 tests |
| 5 US5 (P3) | T031–T032 | US5 | 1 |
| 6 Polish | T033–T036 | — | 2 tests |
| **Total** | **36** | **5** | **11** |
