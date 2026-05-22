# Tasks: Execution Engine

**Input**: Design documents from `/specs/005-execution-engine/`
**Branch**: `005-execution-engine` | **Date**: 2026-05-20
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

---

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Maps to user story from spec.md (US1–US5)
- All file paths are relative to repo root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the `src/execution/` package so all subsequent modules have a home.

- [x] T001 Create `src/execution/` package directory with empty skeleton files: `__init__.py`, `models.py`, `kill_switch.py`, `preflight.py`, `audit_logger.py`, `position_manager.py`, `execution_engine.py`

**Checkpoint**: `from src.execution import __init__` does not raise ImportError.

---

## Phase 2: Foundational — Data Models (blocks all user stories)

**Purpose**: All execution engine entities in one file. Zero MT5 imports. Every other module depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T002 Implement `AuditAction` enum (8 values: ORDER_PLACED, ORDER_REJECTED, TRAILING_STOP_UPDATED, BREAKEVEN_SET, PARTIAL_CLOSE, FULL_CLOSE, SL_MODIFICATION_FAILED, POSITION_EXTERNALLY_CLOSED) and all 5 dataclasses (`ExecutionSignal`, `OrderTicket`, `PositionState`, `TradeAuditEntry`, `KillSwitchState`) per `data-model.md` and `contracts/execution_engine.md` in `src/execution/models.py`. `TradeAuditEntry` must include the 3 constitution-required fields: `max_loss_usd`, `entry_reason`, `exit_reason` (FR-017 / C1 + C2 fix)
- [x] T003 Write unit tests for entity instantiation, field defaults, `PositionState` `current_sl` direction invariant, `TradeAuditEntry` Optional-field contract, and all 8 `AuditAction` values present in `tests/unit/test_execution_models.py`

**Checkpoint**: `python -c "from src.execution.models import AuditAction, ExecutionSignal, PositionState, TradeAuditEntry, KillSwitchState"` succeeds; T003 tests pass.

---

## Phase 3: US4 (P1) — Kill-Switch Safety Mechanism

**Goal**: Operator can halt all new order placement from any terminal without restarting the bot. Existing open positions continue to be managed normally.

**Independent Test**: `activate_kill_switch()` → `is_kill_switch_active()` returns True → delete file → `is_kill_switch_active()` returns False.

- [x] T004 [P] [US4] Implement `activate_kill_switch()`, `deactivate_kill_switch()`, `is_kill_switch_active()` with atomic temp-file-rename write (`Path.replace()`) and file-absent-defaults-to-False safety (ADR-0001) in `src/execution/kill_switch.py`
- [x] T005 [P] [US4] Write unit tests for activate/deactivate cycle, file-absent returns False (safe default), malformed JSON returns False, and that `activate_kill_switch()` always writes valid JSON in `tests/unit/test_execution_kill_switch.py`

**Checkpoint**: Kill-switch activation/deactivation cycle works; all edge cases (absent file, corrupt JSON) return False safely.

---

## Phase 4: US5 (P1) — Full Trade Audit Trail

**Goal**: Every trade action produces a structured `TradeAuditEntry` appended to `logs/trades.json` under a single module-level lock. Write failures must never block trade execution.

**Independent Test**: Call `write_audit_entry()` with a mocked `ORDER_PLACED` entry → verify entry exists in `logs/trades.json` → simulate IOError → verify no exception raised and trade flow continues.

- [x] T006 [P] [US5] Implement `write_audit_entry()` and `write_audit_entries()` with module-level `AUDIT_LOG_LOCK = threading.Lock()`, append-to-JSON-array logic, and silent write-failure handling that logs to stderr without raising (FR-018) in `src/execution/audit_logger.py`. Callers must populate `max_loss_usd` + `entry_reason` for `ORDER_PLACED` entries and `exit_reason` for `PARTIAL_CLOSE` / `FULL_CLOSE` / `POSITION_EXTERNALLY_CLOSED` entries (FR-017 / C1+C2 fix)
- [x] T007 [P] [US5] Write unit tests for all 8 `AuditAction` types produce valid entries, `write_audit_entry()` does not raise on IOError, concurrent writes from two threads do not corrupt the JSON array in `tests/unit/test_execution_audit_logger.py`
- [x] T008 [US5] Migrate `OrderManager._log_trade()` in `src/broker/order_manager.py` to delegate to `audit_logger.write_audit_entry()`, removing `self._log_lock` usage for log writes — eliminates dual-lock race condition on `logs/trades.json` (ADR-0003 risk, plan.md Risk #3). **C3 note**: `order_manager.py` already has uncommitted changes on this branch (timeout guard `_call_with_timeout()` + margin-level check added pre-T008). Implementer must inspect current diff before editing and ensure the timeout + margin rejection paths also route through `audit_logger.write_audit_entry()` rather than the legacy `_log_trade()`
- [x] T009 [US5] Update `tests/unit/test_broker_order_manager.py` to verify `OrderManager` now routes log writes through `audit_logger.write_audit_entry()` and confirm no `_log_lock` / `AUDIT_LOG_LOCK` race in the combined path

**Checkpoint**: Single lock owns `logs/trades.json`; `OrderManager._log_trade()` retired; write failure confirmed non-blocking in test.

---

## Phase 5: US1 (P1) — Order Placement with SL and TP  🎯 MVP

**Goal**: System places a XAUUSD market order with SL and TP set atomically at entry, only after all 5 pre-flight checks pass in cheapest-first order.

**Independent Test**: Supply synthetic `ExecutionSignal` (valid direction, `lot_size > 0`, valid prices) with mocked MT5 → verify `order_manager.place_order()` called once with SL = `sl_price` and TP = `tp2_price` → verify `ORDER_PLACED` audit entry returned → for each rejection scenario (kill-switch, pyramiding, drawdown, margin, min-stop): verify `ORDER_REJECTED` entry returned and no MT5 broker call made for the cheapest rejections.

- [x] T010 [US1] Implement `check_kill_switch()` (delegates to `is_kill_switch_active()`, returns `(bool, str)`) and `check_existing_position()` (dict lookup only, no MT5) in `src/execution/preflight.py`
- [x] T011 [US1] Implement `check_daily_drawdown()` (delegates to `src.risk.drawdown_guard.check_drawdown()` — **note**: `check_drawdown()` returns `TradeAllowedResult(allowed, reason)`; unpack with `result.allowed, result.reason` before returning `(bool, str)`), `check_margin_sufficiency()` (calls `mt5.order_check()`), and `check_minimum_stop_distance()` (calls `mt5.symbol_info("XAUUSD").trade_stops_level`) in `src/execution/preflight.py`
- [x] T012 [US1] Implement `run_preflight()` orchestrator — fixed check order (kill-switch → pyramiding → drawdown → margin → min-stop), short-circuit on first `False` return (D-006); returns `(True, "")` when all pass in `src/execution/preflight.py`
- [x] T013 [US1] Write unit tests for all 5 checks individually, `run_preflight()` short-circuit order (assert MT5 calls are NOT made when kill-switch blocks), and all US1 acceptance scenarios (drawdown rejection, margin rejection, min-stop rejection, kill-switch rejection) in `tests/unit/test_execution_preflight.py`
- [x] T014 [US1] Implement `ExecutionEngine.__init__()` (stores `order_manager`, `config`, `kill_switch_path`; initialises `self._positions: dict[int, PositionState] = {}`) and `execute_signal()` (preflight → `order_manager.place_order()` → build `PositionState` → write `ORDER_PLACED` audit entry; on any failure: write `ORDER_REJECTED` entry; never raises) in `src/execution/execution_engine.py`. When building `ORDER_PLACED` entry: set `entry_reason = exec_signal.entry_signal.reason` (CHK009 fix) and `max_loss_usd` from `order_manager.place_order()` result
- [x] T015 [US1] Write unit tests for `execute_signal()` happy path (ORDER_PLACED returned, position added to `self._positions`), all 5 rejection scenarios (ORDER_REJECTED returned, no broker call for kill-switch and pyramiding), and broker connection failure (ORDER_REJECTED with `rejection_reason="broker timeout"`, no partial state) in `tests/unit/test_execution_engine.py`

**Checkpoint**: US1 fully functional with mocked MT5. `execute_signal()` can place an order end-to-end and produce an ORDER_PLACED audit entry. **MVP complete.**

---

## Phase 6: US2 (P2) — Trailing Stop Management

**Goal**: After entry, stop loss follows price in the trade direction to lock in unrealised profits. SL never moves backward.

**Independent Test**: Build `PositionState` (LONG, entry=1800.0, SL=1780.0, `trailing_activated=False`) → `evaluate_trailing_stop(position, current_price=1831.0, config)` → verify returned state has `trailing_activated=True` and `current_sl = 1831.0 - trailing_distance` → call again with `current_price=1829.0` (retracing) → verify SL unchanged.

- [x] T016 [US2] Implement `evaluate_trailing_stop()` pure function — LONG: activate when `current_price >= entry_price + activation_distance`; `new_sl = current_price - trailing_distance`; apply only when `new_sl > position.current_sl`; SHORT: symmetric — returns `(PositionState, Optional[TradeAuditEntry])`, no MT5 calls in `src/execution/position_manager.py`
- [x] T017 [US2] Implement `_apply_sl_modification()` — sends `TRADE_ACTION_SLTP` request via `mt5.order_send()`; retries once on failure; on second failure writes `SL_MODIFICATION_FAILED` audit entry; returns `(success: bool, reason: str)` in `src/execution/position_manager.py`
- [x] T018 [US2] Write unit tests for trailing activation threshold (LONG and SHORT), unidirectional invariant (SL never decreases for LONG, never increases for SHORT), no modification when price below activation distance, and broker rejection triggers single retry then `SL_MODIFICATION_FAILED` entry in `tests/unit/test_execution_position_manager.py`

**Checkpoint**: `evaluate_trailing_stop()` correct for both directions; `_apply_sl_modification()` retries once then logs failure.

---

## Phase 7: US3 (P2) — Partial Close at First Profit Target

**Goal**: When price reaches TP1, close 50% of position at market and move remaining SL to entry price — converting an at-risk trade into a free-ride.

**Independent Test**: Build `PositionState` with `partial_close_done=False` → simulate price at TP1 → `apply_partial_close()` → verify counter-direction order sent with `lot_size * tp1_close_ratio` (rounded to 0.01) and `position=ticket_id` → verify `PositionState.lot_size` reduced → verify `PositionState.current_sl == entry_price` → verify `PARTIAL_CLOSE` and `BREAKEVEN_SET` audit entries returned.

- [x] T019 [US3] Implement `apply_partial_close()` — calculate `close_lots = round(position.lot_size * config["tp1_close_ratio"], 2)`, send counter-direction `TRADE_ACTION_DEAL` with `"position": ticket_id` via `order_manager`, on success: reduce `PositionState.lot_size`, set `partial_close_done=True`, call `_apply_sl_modification()` with `new_sl=entry_price` (BREAKEVEN_SET); on broker failure: log `PARTIAL_CLOSE` failure entry, return unchanged state — in `src/execution/position_manager.py`
- [x] T020 [US3] Implement `reconcile_positions()` — call `mt5.positions_get(symbol="XAUUSD")`; for each ticket in engine dict absent from broker response: write `POSITION_EXTERNALLY_CLOSED` audit entry and remove from dict; return `(pruned_dict, audit_entries)` in `src/execution/position_manager.py`
- [x] T021 [US3] Implement `manage_positions()` bar-level entry point — per-position step order: (1) `reconcile_positions()`, (2) TP2 hit → full close via `order_manager`, (3) TP1 hit and `not partial_close_done` → `apply_partial_close()`, (4) `evaluate_trailing_stop()` → if new SL: `_apply_sl_modification()`; returns `(updated_positions_dict, all_audit_entries)` in `src/execution/position_manager.py`
- [x] T022 [US3] Write unit tests for partial close (lot ratio applied, lots rounded to 0.01, breakeven SL set), `reconcile_positions()` (absent ticket detected and `POSITION_EXTERNALLY_CLOSED` written), TP2 full close (position removed from dict), lot-mismatch edge case (`close_lots > actual_lots` logs warning without crash), TP2 and trailing-update on same bar (only one close action results) in `tests/unit/test_execution_position_manager.py`

**Checkpoint**: Full position lifecycle covered — open → trail → partial close → free-ride → TP2 close or external close.

---

## Phase 8: Polish & Integration

**Purpose**: Wire orchestrator, update config, finalise exports, run integration test, verify coverage gate.

- [x] T023 Implement `ExecutionEngine.manage_open_positions()` (delegates to `manage_positions()`, calls `write_audit_entries()` on returned entries, returns `list[TradeAuditEntry]`) and `open_positions` property (read-only `dict` view of `self._positions`) in `src/execution/execution_engine.py`
- [x] T024 Write unit tests for `manage_open_positions()` — kill-switch active allows position management while blocking new `execute_signal()` calls (US4 acceptance S2), and end-to-end mock round-trip confirming audit entries returned in `tests/unit/test_execution_engine.py`
- [x] T025 Add `execution:` configuration block (`trailing.activation_distance`, `trailing.trailing_distance`, `partial_close.tp1_close_ratio`, `magic_number`, `slippage_points`, `kill_switch_path`, `audit_log_path`) to `config.yaml`
- [x] T026 [P] Update `src/execution/__init__.py` with all public exports: `ExecutionEngine`, `ExecutionSignal`, `PositionState`, `TradeAuditEntry`, `AuditAction`, `activate_kill_switch`, `deactivate_kill_switch`, `is_kill_switch_active`
- [x] T027 Write integration test for complete round-trip on MT5 demo account — place order → confirm SL set at entry time (SC-001) → simulate trailing activation → simulate TP1 hit → partial close + breakeven SL → simulate TP2 hit → full close — verify one audit entry per action, no silent executions (SC-006, SC-008) in `tests/integration/test_execution_integration.py`
- [x] T028 [P] Run `pytest --cov=src/execution --cov-report=term-missing` and verify line coverage ≥ 80% for all `src/execution/` modules (SC-007)

**Checkpoint**: All tests pass; coverage ≥ 80%; T027 integration round-trip succeeds on MT5 demo.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — **BLOCKS all user story phases**
- **Phase 3 (US4)** and **Phase 4 (US5)**: Both depend only on Phase 2; independent of each other — can run in parallel
- **Phase 5 (US1)**: Depends on Phases 2, 3, and 4 complete (`preflight.py` uses `kill_switch.py`; `execute_signal()` uses `audit_logger.py`)
- **Phase 6 (US2)**: Depends on Phase 2 only (pure function, no audit_logger/kill_switch import) — can start in parallel with Phase 3/4 if team allows
- **Phase 7 (US3)**: Depends on Phase 6 complete (extends `position_manager.py`)
- **Phase 8 (Polish)**: Depends on Phases 5, 6, and 7 all complete

### User Story Dependencies

| Story | Priority | Depends On | Parallelizable With |
|-------|----------|-----------|---------------------|
| US4 (Kill-Switch) | P1 | Phase 2 | US5, US2 |
| US5 (Audit Trail) | P1 | Phase 2 | US4, US2 |
| US1 (Order Placement) | P1 | US4 + US5 + Phase 2 | None — must follow US4+US5 |
| US2 (Trailing Stop) | P2 | Phase 2 only | US4, US5 |
| US3 (Partial Close) | P2 | US2 (same file) | None — sequential after US2 |

### Within Each Phase

- Tests written alongside (or just before) implementation — failing test first, then implementation
- T010 and T011 are sequential (same file, different function groups)
- T012 (`run_preflight`) requires T010 and T011 complete
- T014 (`execute_signal`) requires T012 complete
- T019–T021 are sequential (same file, each function calls the previous)
- T023 (`manage_open_positions`) requires T021 (`manage_positions`) complete

### Parallel Opportunities

- **T004 + T006**: `kill_switch.py` and `audit_logger.py` are independent files — implement simultaneously
- **T005 + T007**: Their test files — also independent
- **T016** (trailing stop pure logic) can begin as soon as Phase 2 is complete — independent of Phases 3/4
- **T023, T025, T026** in Phase 8 are different files — parallelizable

---

## Parallel Example: After Phase 2 (Two Developers)

```bash
# Developer A — Phase 3 + parallel start on Phase 6
Task: T004 — Implement src/execution/kill_switch.py
Task: T005 — Write tests/unit/test_execution_kill_switch.py
Task: T016 — Implement evaluate_trailing_stop() in src/execution/position_manager.py  # pure function, no deps

# Developer B — Phase 4
Task: T006 — Implement src/execution/audit_logger.py
Task: T007 — Write tests/unit/test_execution_audit_logger.py
Task: T008 — Migrate OrderManager._log_trade() → audit_logger (CRITICAL dual-lock fix)
Task: T009 — Update tests/unit/test_broker_order_manager.py
```

---

## Implementation Strategy

### MVP (US4 + US5 + US1 — minimum viable execution)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational models
3. Complete Phase 3: Kill-switch (US4)
4. Complete Phase 4: Audit trail (US5) — **including T008 dual-lock migration (highest-risk task)**
5. Complete Phase 5: Order placement (US1)
6. **STOP and VALIDATE**: Place order on MT5 demo, activate kill-switch, verify audit log
7. MVP live — bot can open positions safely with full audit trail and emergency stop

### Incremental Delivery

1. MVP above → operators can place + audit orders; kill-switch armed
2. Add Phase 6 (US2 Trailing Stop) → unrealised profits protected automatically
3. Add Phase 7 (US3 Partial Close) → free-ride mechanic active; risk-adjusted returns improve
4. Phase 8 → full integration test, coverage gate, config complete

---

## Notes

- **T008 is the highest-risk task** — migrating a live log writer. Run T027 integration test immediately after T008 to verify no JSON array corruption before merging.
- `apply_partial_close()` (T019): always `round(close_lots, 2)` before MT5 submission — avoids `TRADE_RETCODE_INVALID_VOLUME` (plan.md Risk #2).
- All MT5 calls (`check_margin_sufficiency`, `check_minimum_stop_distance`, `reconcile_positions`, `_apply_sl_modification`) must be mocked with `pytest-mock` in unit tests — never require a live connection.
- `trailing_activated` and `partial_close_done` flags are **lost on process restart** — known limitation per ADR-0002. Operator must verify position flags manually after bot restart mid-position.
- [P] marker = different files, no incomplete task dependencies — safe to run simultaneously.
