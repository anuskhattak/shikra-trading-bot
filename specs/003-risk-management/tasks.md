# Tasks: Risk Management Module

**Input**: Design documents from `specs/003-risk-management/`
**Branch**: `003-risk-management`
**Date**: 2026-05-16
**Prerequisites**: plan.md ✅ | spec.md ✅ | data-model.md ✅ | contracts/risk_manager.md ✅

**Tests**: Included — SC-008 requires ≥ 80% unit test coverage for all risk modules.

**Organization**: Tasks grouped by user story. Each story is independently implementable and testable.

---

## Dependencies & Execution Order

```
Phase 1 (Setup & Models) — BLOCKS all phases
    ↓
Phase 2 (US1+US2: lot_calculator) ─┐
Phase 3 (US3: drawdown_guard)      ├─ parallel after Phase 1
Phase 4 (US4: trade_limits)        ├─ parallel after Phase 1
Phase 5 (US5: recovery_mode)       ┘
    ↓ all complete
Phase 6 (Orchestrator) — BLOCKS Polish
    ↓
Phase 7 (Polish & Coverage)
```

**Parallel opportunities**: T002/T003 within Phase 1; test tasks T005/T007/T009/T011 can run in parallel across phases (different files); T016/T017 in Phase 7.

---

## Phase 1: Setup & Models (Blocking)

**Purpose**: Shared infrastructure and data model — prerequisite for all user story phases.

- [x] T001 Create `src/risk/` directory with empty `__init__.py` placeholder
- [x] T002 [P] Add `risk:` section to `config.yaml` per data-model.md Config Schema — fields: risk_percent, max_lot_size, min_lot_size, pip_value_per_lot, sl_atr_multiplier, tp1_rr_ratio, tp2_rr_ratio, max_daily_drawdown, max_trades_per_day, max_trades_per_session, cooldown_after_sl_hours, max_consecutive_losses, recovery_lot_multiplier, recovery_min_confidence, recovery_profit_target_pips
- [x] T003 [P] Add `logs/risk_events.json` placeholder and path to `.gitignore`
- [x] T004 Implement `src/risk/models.py` — enums (`RecoveryReason`, `BlockReason`) + dataclasses (`RiskCalculation`, `RiskState`, `TradeAllowedResult`) with all fields from data-model.md; include invariant comments on `RiskCalculation`

**Checkpoint**: `from src.risk.models import RiskCalculation, RiskState, TradeAllowedResult` imports without error.

---

## Phase 2: US1 + US2 — Lot Size & SL/TP Calculation (P1 — Core)

**Goal**: Produce correctly-sized lots and ATR-based SL/TP prices for any valid signal — the core capital-allocation output.

**Independent Test**: `pytest tests/unit/test_risk_lot_calculator.py` — all 13 tests pass with zero MT5 dependency.

### Tests first (must FAIL before implementation)

- [x] T005 [P] [US1] Write failing unit tests for lot sizing in `tests/unit/test_risk_lot_calculator.py`:
  - `test_lot_size_formula_correct` — balance=10000, risk=1%, SL=20 pips → formula result = 0.50 (SC-001)
  - `test_lot_size_clamped_to_minimum` — extremely wide SL → lot clamped to 0.01 (FR-002, SC-006)
  - `test_lot_size_clamped_to_maximum` — large balance / small SL → lot clamped to max_lot_size (FR-003, SC-006)
  - `test_hard_cap_5pct_applied` — risk_amount > balance×0.05 → lot reduced so loss ≤ 5% balance (FR-004)

- [x] T005b [P] [US2] Append failing SL/TP tests to `tests/unit/test_risk_lot_calculator.py`:
  - `test_sl_long_below_entry` — LONG direction → SL < entry (FR-006)
  - `test_sl_short_above_entry` — SHORT direction → SL > entry (FR-006, SC-007)
  - `test_sl_raises_on_invalid_atr` — d1_atr ≤ 0 → raises ValueError (FR-006a)
  - `test_sl_raises_on_invalid_entry` — entry ≤ 0 → raises ValueError (FR-006a, added)
  - `test_sl_uses_atr_multiplier` — sl_distance = D1_ATR × sl_atr_multiplier (FR-007)
  - `test_tp_long_prices_correct` — entry=2350, D1_ATR=20, mult=1.5 → SL=2320, TP1=2395, TP2=2440 (SC-003)
  - `test_tp_short_prices_correct` — SHORT: SL above entry, TP1/TP2 below entry (FR-011, SC-007)
  - `test_tp_ordering_long` — SL < entry < TP1 < TP2 for LONG (FR-011)
  - `test_tp_ordering_short` — TP2 < TP1 < entry < SL for SHORT (FR-011)

### Implementation

- [x] T006 [US1] [US2] Implement `src/risk/lot_calculator.py`:
  - `XAUUSD_PIP_VALUE: float = 10.0` — module constant with comment (D-004)
  - `calculate_lot_size(balance, risk_percent, sl_distance, pip_value_per_lot, max_lot, min_lot) -> float` — `sl_distance` in price units; 5% hard cap before clamping (FR-001–FR-005, D-007)
  - `calculate_sl_price(entry, direction, d1_atr, sl_atr_multiplier) -> float` — raises ValueError on invalid ATR/entry (FR-006, FR-006a)
  - `_calculate_sl_distance(d1_atr, sl_atr_multiplier) -> float` — private helper; not exported (FR-007)
  - `calculate_tp_prices(entry, sl_price, direction, tp1_rr, tp2_rr) -> tuple[float, float]` (FR-008–FR-011)

**Checkpoint**: `pytest tests/unit/test_risk_lot_calculator.py` — all 13 tests pass. ✓

---

## Phase 3: US3 — Daily Drawdown Guard (P1 — Safety)

**Goal**: Block all trading for the rest of the day once daily loss exceeds the configured threshold.

**Independent Test**: `pytest tests/unit/test_risk_drawdown_guard.py` — all 7 tests pass.

### Tests first

- [x] T007 [P] [US3] Write failing unit tests in `tests/unit/test_risk_drawdown_guard.py`:
  - `test_drawdown_blocks_at_limit` — equity=9400, start=10000, limit=5% → allowed=False (SC-002)
  - `test_drawdown_allows_below_limit` — equity=9600, start=10000, limit=5% → allowed=True
  - `test_drawdown_reason_string_correct` — reason contains "6.0%" and "5.0%"
  - `test_drawdown_at_exact_limit_blocks` — equity=9500, limit=5% → drawdown=5.0% → blocked (boundary)
  - `test_reset_updates_day_start_equity` — `reset_daily_state` sets day_start_equity to current_equity
  - `test_reset_clears_trades_today` — trades_today resets to 0 after reset (FR-015)
  - `test_startup_mid_day_initialization` — new `RiskState(day_start_equity=current_equity)` reflects current equity; verifies mid-day restart limitation documented in FR-015a

### Implementation

- [x] T008 [US3] Implement `src/risk/drawdown_guard.py`:
  - `check_drawdown(day_start_equity, current_equity, max_pct) -> TradeAllowedResult` (FR-012–FR-014)
  - `reset_daily_state(state, current_equity) -> RiskState` — call at UTC 00:00 (FR-015)
  - `get_drawdown_pct(day_start_equity, current_equity) -> float` — returns 0.0 when equity ≥ start
  - Append JSON entry to `logs/risk_events.json` on drawdown block; silent fail on write error (NFR-005)

**Checkpoint**: `pytest tests/unit/test_risk_drawdown_guard.py` — all tests pass.

---

## Phase 4: US4 — Trade Limits (P2)

**Goal**: Enforce per-day and per-session trade caps and a cooldown period after each SL hit.

**Independent Test**: `pytest tests/unit/test_risk_trade_limits.py` — all 10 tests pass.

### Tests first

- [x] T009 [P] [US4] Write failing unit tests in `tests/unit/test_risk_trade_limits.py`:
  - `test_daily_limit_blocks_when_reached` — trades_today=5, max=5 → blocked (FR-017)
  - `test_daily_limit_allows_below` — trades_today=4, max=5 → allowed
  - `test_session_limit_blocks` — session_trades["LONDON"]=2, max=2 → blocked (FR-018)
  - `test_cooldown_blocks_within_period` — last_sl 30 min ago, cooldown=2h → blocked (FR-019)
  - `test_cooldown_allows_after_period` — last_sl 3 hours ago, cooldown=2h → allowed
  - `test_cooldown_allows_when_no_sl` — last_sl_time=None → no cooldown applied
  - `test_record_trade_opened_increments_counters` — trades_today and session_trades both increment (FR-020)
  - `test_record_sl_hit_sets_time` — last_sl_time = current_time (UTC) (FR-021)
  - `test_record_sl_hit_increments_losses` — consecutive_losses += 1 (FR-021)
  - `test_record_trade_won_resets_losses` — consecutive_losses → 0 (FR-022)

### Implementation

- [x] T010 [US4] Implement `src/risk/trade_limits.py`:
  - `is_trade_limit_allowed(state, config, current_time, session) -> TradeAllowedResult` — checks daily → session → cooldown in order (FR-016–FR-019)
  - `record_trade_opened(state, session) -> RiskState` (FR-020)
  - `record_sl_hit(state, current_time) -> RiskState` — current_time must be UTC (FR-021)
  - `record_trade_won(state) -> RiskState` (FR-022)

**Checkpoint**: `pytest tests/unit/test_risk_trade_limits.py` — all tests pass.

---

## Phase 5: US5 — Recovery Mode (P3)

**Goal**: After N consecutive SL hits, reduce lot size and filter out low-confidence signals until the system recovers enough pips.

**Independent Test**: `pytest tests/unit/test_risk_recovery_mode.py` — all 7 tests pass.

### Tests first

- [x] T011 [P] [US5] Write failing unit tests in `tests/unit/test_risk_recovery_mode.py`:
  - `test_recovery_activates_at_loss_threshold` — consecutive_losses=3, max=3 → in_recovery_mode=True (FR-023, SC-004)
  - `test_recovery_not_active_below_threshold` — consecutive_losses=2, max=3 → in_recovery_mode=False
  - `test_recovery_lot_reduced` — normal_lot=0.10, multiplier=0.5 → result=0.05 (FR-024, SC-004)
  - `test_signal_rejected_in_recovery_low_confidence` — confidence=0.75, min=0.80 → False (FR-025, SC-005)
  - `test_signal_allowed_in_recovery_high_confidence` — confidence=0.82, min=0.80 → True (FR-025)
  - `test_recovery_exits_at_profit_target` — recovery_profit_pips=50, target=50 → in_recovery_mode=False (FR-026)
  - `test_recovery_profit_accumulated` — update_recovery_profit adds pips_gained_price_units to state.recovery_profit_pips (FR-026, FR-028)

### Implementation

- [x] T012 [US5] Implement `src/risk/recovery_mode.py`:
  - `check_recovery_status(state, config) -> RiskState` — activates/exits recovery; logs events (FR-023, FR-027)
  - `is_signal_allowed_in_recovery(confidence, recovery_min_confidence) -> bool` (FR-025)
  - `apply_recovery_lot(lot_size, recovery_lot_multiplier) -> float` — called before final clamping (FR-024)
  - `update_recovery_profit(state, pips_gained_price_units) -> RiskState` — called by spec004 (Execution Engine) after each closed trade; exits recovery when target reached (FR-026, FR-028)
  - Append JSON entry to `logs/risk_events.json` on recovery enter/exit; silent fail on write error (NFR-005)

**Checkpoint**: `pytest tests/unit/test_risk_recovery_mode.py` — all tests pass.

---

## Phase 6: Orchestrator + Integration Tests (All Stories)

**Goal**: Wire all sub-modules into single entry point `evaluate_trade_risk()` — the interface consumed by spec004 (Execution Engine).

**Independent Test**: `pytest tests/integration/test_risk_pipeline.py` — all 6 tests pass.

### Tests first

- [x] T013 [P] Write failing integration tests in `tests/integration/test_risk_pipeline.py`:
  - `test_full_evaluation_returns_risk_calculation` — valid EntrySignal → RiskCalculation with lot > 0
  - `test_none_signal_returns_zero_lot` — direction=NONE → lot_size=0.0, sl_price=0.0, tp prices=0.0
  - `test_recovery_mode_reduces_lot_in_pipeline` — state.consecutive_losses=3 → lot halved end-to-end
  - `test_drawdown_block_returns_zero_lot` — equity below threshold → lot=0.0, reason populated
  - `test_rr_ratios_correct_end_to_end` — full pipeline TP1/TP2 match expected R:R from spec (SC-003)
  - `test_state_immutability` — input state unchanged after evaluate_trade_risk; new state returned (NFR-003)

### Implementation

- [x] T014 Implement `src/risk/risk_manager.py`:
  - `evaluate_trade_risk(entry_signal, balance, current_equity, d1_atr, state, config) -> tuple[RiskCalculation, RiskState]` (D-006, contracts/risk_manager.md)
  - Guard evaluation order: drawdown check → trade limits → recovery check → lot calc → SL/TP calc → assemble RiskCalculation
  - `_zero_risk_calc(reason, in_recovery) -> RiskCalculation` private helper — lot/SL/TP all 0.0
  - Returns `(zero_risk_calc, state)` on any block — never raises on valid inputs
  - `entry_price = (entry_signal.entry_zone_top + entry_signal.entry_zone_bottom) / 2` — midpoint of zone per D-003
  - On `allowed=True`: append DEBUG entry to `logs/risk_events.json` — lot_size, sl_price, tp1_price, tp2_price, max_loss_usd, reason="ALLOWED", timestamp UTC; silent fail on write error (NFR-006)

**Checkpoint**: `pytest tests/integration/test_risk_pipeline.py` — all tests pass.

---

## Phase 7: Polish & Coverage

- [x] T015 Update `src/risk/__init__.py` — export public API: `evaluate_trade_risk`, `RiskCalculation`, `RiskState`, `TradeAllowedResult`, `reset_daily_state`, `record_trade_opened`, `record_sl_hit`, `record_trade_won`
- [x] T016 [P] Run `pytest --cov=src/risk --cov-report=term-missing` — confirm ≥ 80% coverage across all modules (SC-008)
- [x] T017 [P] Run `grep -r "MetaTrader5\|import mt5" src/risk/` — must return zero results (SC-009, NFR-001)
- [x] T017b [P] Run `mypy src/risk/ --strict` — verify all type hints correct; run `ruff check src/risk/` — verify docstring compliance (NFR-004)
- [x] T018 Update `specs/003-risk-management/checklists/implementation-review.md` — mark all CHK items complete

---

## Task Summary

| Phase | User Story | Tasks | Count |
|-------|-----------|-------|-------|
| Phase 1 — Setup & Models | — | T001–T004 | 4 |
| Phase 2 — Lot/SL/TP | US1 + US2 | T005, T005b, T006 | 3 |
| Phase 3 — Drawdown Guard | US3 | T007–T008 | 2 |
| Phase 4 — Trade Limits | US4 | T009–T010 | 2 |
| Phase 5 — Recovery Mode | US5 | T011–T012 | 2 |
| Phase 6 — Orchestrator | All | T013–T014 | 2 |
| Phase 7 — Polish | — | T015–T018, T017b | 5 |
| **Total** | | | **20** |

---

## Implementation Strategy

### MVP (User Story 1 + 2 Only — Core Calculation)

1. Complete Phase 1 (Setup & Models)
2. Complete Phase 2 (US1+US2: `lot_calculator.py`)
3. **Validate**: `pytest tests/unit/test_risk_lot_calculator.py` — lot sizing and SL/TP verified
4. Proceed to remaining stories

### Full Delivery Order (Priority: P1 → P2 → P3)

1. Phase 1 — Models (blocking)
2. Phase 2 — US1+US2: lot_calculator (P1 Core)
3. Phase 3 — US3: drawdown_guard (P1 Safety) ← parallel with Phase 2 if team allows
4. Phase 4 — US4: trade_limits (P2)
5. Phase 5 — US5: recovery_mode (P3)
6. Phase 6 — Orchestrator wires all above
7. Phase 7 — Coverage + cleanup

### Notes

- Tests must be written and confirmed FAILING before implementation
- Each phase has an independent Checkpoint — validate before moving on
- No `import MetaTrader5` allowed in any `src/risk/` file (NFR-001)
- All timestamps UTC; `datetime.utcnow()` throughout
- `RiskState` is never mutated in place — always return new instance (NFR-003)
