# Implementation Plan: Execution Engine

**Branch**: `005-execution-engine` | **Date**: 2026-05-20 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/005-execution-engine/spec.md`

---

## Summary

Build `src/execution/` — the terminal stage of the Shikra pipeline. The engine accepts a validated `ExecutionSignal` (EntrySignal + RiskCalculation), runs five pre-flight safety checks (kill-switch, pyramiding guard, drawdown, margin, minimum stop distance), places a XAUUSD market order with mandatory SL+TP via the existing `OrderManager`, then actively manages every open position through trailing stop adjustment, partial close at TP1 with breakeven SL, and full close at TP2 — logging every action as an immutable `TradeAuditEntry` to `logs/trades.json`.

---

## Technical Context

**Language/Version**: Python 3.10+  
**Primary Dependencies**: MetaTrader5, loguru, pytest, pytest-mock (all already present)  
**Storage**: JSON files — `logs/trades.json` (audit), `logs/kill_switch.json` (kill-switch state)  
**Testing**: pytest + pytest-mock (MT5 mocked in unit tests; live demo for integration)  
**Target Platform**: Windows (MT5 Python SDK is Windows-only)  
**Project Type**: single  
**Performance Goals**: Order placement < 3 seconds (SC-002); trailing/partial-close evaluated within one H1 bar (SC-003, SC-004); kill-switch effective within one eval cycle ≤ 60 seconds (SC-005)  
**Constraints**: MT5 API is not thread-safe — all broker calls from main thread; XAUUSD only; no pyramiding; Windows-only deployment

---

## Constitution Check

*GATE: Checked against CLAUDE.md core guarantees.*

| Guarantee | Requirement | Status |
|-----------|------------|--------|
| Signal Integrity | Every signal validated via pre-flight before broker call | ✅ PASS — `run_preflight()` enforces FR-001 through FR-007 |
| Risk First | SL + TP set atomically at order placement | ✅ PASS — FR-002: SL/TP submitted in same `order_send` request; no separate step |
| Risk First | Daily drawdown blocks new orders | ✅ PASS — FR-004: reuses `check_drawdown()` from spec003 |
| Risk First | Every entry logs: entry price, SL, TP, max loss USD | ✅ PASS — FR-017: `TradeAuditEntry` captures all fields |
| Auditability | Every action produces a structured log entry | ✅ PASS — FR-016: `AuditAction` enum covers all 8 event types |
| Auditability | Audit log write failure does NOT block trade | ✅ PASS — FR-018: `write_audit_entry()` swallows write exceptions |
| Quality Gates | Unit test coverage ≥ 80% | ✅ PLANNED — SC-007; five unit test files targeting all modules |
| Quality Gates | Integration test: full round-trip on MT5 demo | ✅ PLANNED — SC-008 |
| Documentation | Docstrings on all public functions | ✅ ENFORCED — per CLAUDE.md Code Standards |

**Constitution result: PASS — all gates satisfied. No complexity violations.**

---

## Architecture

```
EntrySignal (spec002)  +  RiskCalculation (spec003)
           │                        │
           └────────────────────────┘
                        │
               ExecutionSignal (models.py)
                        │
                        ▼
          ┌─────────────────────────────┐
          │   ExecutionEngine           │
          │   execution_engine.py       │
          │                             │
          │  execute_signal()           │
          │    │                        │
          │    ├─ preflight.py          │
          │    │    run_preflight()     │
          │    │    ├─ kill_switch      │
          │    │    ├─ pyramiding       │
          │    │    ├─ drawdown         │
          │    │    ├─ margin           │
          │    │    └─ min_stop_dist    │
          │    │                        │
          │    ├─ OrderManager          │──→ MT5 broker
          │    │   place_order()        │
          │    │                        │
          │    └─ audit_logger.py       │──→ logs/trades.json
          │         write_audit_entry() │
          │                             │
          │  manage_open_positions()    │
          │    │                        │
          │    ├─ position_manager.py   │
          │    │    reconcile()         │
          │    │    eval_trailing()     │──→ MT5 SLTP modify
          │    │    apply_partial_cls() │──→ MT5 counter-order
          │    │    full_close()        │──→ MT5 close
          │    │                        │
          │    └─ audit_logger.py       │──→ logs/trades.json
          └─────────────────────────────┘
```

---

## Project Structure

### Documentation (this feature)

```text
specs/005-execution-engine/
├── plan.md              ← this file
├── research.md          ← Phase 0: all design decisions resolved
├── data-model.md        ← Phase 1: entities, state transitions, validation rules
├── quickstart.md        ← Phase 1: usage guide, config, test commands
├── contracts/
│   └── execution_engine.md  ← Phase 1: full function signatures + error contract
└── tasks.md             ← Phase 2 (/sp.tasks — NOT created by /sp.plan)
```

### Source Code

```text
src/execution/
├── __init__.py                 — public exports
├── models.py                   — ExecutionSignal, PositionState, TradeAuditEntry,
│                                 KillSwitchState, AuditAction
├── kill_switch.py              — activate/deactivate/is_active helpers
├── preflight.py                — run_preflight() + 5 individual check functions
├── audit_logger.py             — thread-safe JSON append; write_audit_entry()
├── position_manager.py         — manage_positions(), evaluate_trailing_stop(),
│                                 apply_partial_close(), reconcile_positions()
└── execution_engine.py         — ExecutionEngine class (main orchestrator)

tests/unit/
├── test_execution_models.py
├── test_execution_kill_switch.py
├── test_execution_preflight.py
├── test_execution_position_manager.py
├── test_execution_audit_logger.py
└── test_execution_engine.py

tests/integration/
└── test_execution_integration.py

logs/
└── kill_switch.json            — created on first activate; absent = inactive (safe default)
```

**Structure Decision**: Single-project layout extending existing `src/` tree. New `src/execution/` module follows identical layout to `src/filters/`, `src/risk/`, `src/broker/` — `models.py` first (no cross-imports), pure functions where possible, single orchestrator class.

---

## Key Design Decisions

### D-001: Kill-Switch — File-Based (`logs/kill_switch.json`)
FR-014 requires the kill-switch to be activatable without restarting the process. File-based flag allows operator write from terminal/script without IPC. Written atomically (temp + rename). In-memory bool cached per cycle for performance. See `research.md` D-001.

### D-002: Position Polling — Synchronous H1 Bar Loop
`manage_open_positions()` called synchronously by the main event loop on each H1 bar close — same cadence as SMC engine. MT5 Python SDK is not thread-safe; all MT5 calls stay on main thread. See `research.md` D-002.

### D-003: Partial Close via Counter-Direction `order_send` with `position=ticket_id`
MT5 has no dedicated partial-close action. Counter-direction market order with `position=ticket_id` is the canonical MT5 partial close pattern. See `research.md` D-003.

### D-004: `TradeAuditEntry` Is a Standalone Dataclass
Does not extend `TradeOrder` from spec001. Different lifecycle (8 action types vs. 1 placement record), different fields, independent audit ownership. See `research.md` D-004.

### D-005: `PositionState` Ownership — Engine-Side Dict, Reconciled Each Bar
Engine holds `dict[int, PositionState]` keyed by ticket ID. `reconcile_positions()` calls `mt5.positions_get()` each bar; absent tickets = externally closed. See `research.md` D-005.

### D-006: Pre-Flight Order — Kill-Switch → Pyramiding → Drawdown → Margin → Min-Stop
Cheapest checks first, MT5 API calls last. Short-circuit on first failure. See `research.md` D-006.

### D-007: `ExecutionSignal` — Composite Dataclass (Not Flattened)
Two-field dataclass wrapping `EntrySignal` + `RiskCalculation`. Preserves provenance, avoids field-name collisions. See `research.md` D-007.

### D-008: Breakeven SL = Entry Price Exactly (No Buffer)
Industry-standard free-ride mechanic. Min stop distance checked before SLTP modification.

### D-009: Stale Position Detection via `mt5.positions_get()` Reconciliation
Absence from broker response = externally closed. Engine dict pruned; `POSITION_EXTERNALLY_CLOSED` audit entry written.

---

## Module Breakdown

### `src/execution/models.py`
- `AuditAction` enum: 8 action types (ORDER_PLACED, ORDER_REJECTED, TRAILING_STOP_UPDATED, BREAKEVEN_SET, PARTIAL_CLOSE, FULL_CLOSE, SL_MODIFICATION_FAILED, POSITION_EXTERNALLY_CLOSED)
- `ExecutionSignal` dataclass: `entry_signal`, `risk_calc`, `signal_id`, `received_at`
- `PositionState` dataclass: ticket_id, direction, entry_price, current_sl, tp1/tp2, lot_size, trailing_activated, partial_close_done, signal_id, opened_at
- `TradeAuditEntry` dataclass: all FR-017 fields (19 fields, most Optional) — includes `max_loss_usd`, `entry_reason`, `exit_reason` per CLAUDE.md constitution (C1+C2 fix)
- `KillSwitchState` dataclass: active, activated_at, activated_by
- Zero MT5 imports.

### `src/execution/kill_switch.py`
- `activate_kill_switch(path, reason)` — atomic write, active=True
- `deactivate_kill_switch(path)` — atomic write, active=False
- `is_kill_switch_active(path)` — read; returns False on any error (safe default)

### `src/execution/preflight.py`
- `check_kill_switch(path)` → `(bool, str)` — reads kill_switch.json
- `check_existing_position(positions, direction)` → `(bool, str)` — in-memory check
- `check_daily_drawdown(day_start_equity, current_equity, max_pct)` → `(bool, str)` — delegates to spec003; **must unpack** `TradeAllowedResult` returned by `check_drawdown()`: `return result.allowed, result.reason`
- `check_margin_sufficiency(lot_size)` → `(bool, str)` — calls `mt5.order_check()`
- `check_minimum_stop_distance(direction, entry_price, sl_price)` → `(bool, str)` — calls `mt5.symbol_info()`
- `run_preflight(exec_signal, positions, day_start_equity, current_equity, config, kill_switch_path)` → `(bool, str)` — orchestrates all 5 checks, short-circuits

### `src/execution/audit_logger.py`
- `AUDIT_LOG_LOCK` — module-level `threading.Lock()` (shared with order_manager's lock via same file path)
- `write_audit_entry(entry: TradeAuditEntry)` — appends to `logs/trades.json`; silent on write failure (FR-018)
- `write_audit_entries(entries: list[TradeAuditEntry])` — batch version, single lock acquire

### `src/execution/position_manager.py`
- `evaluate_trailing_stop(position, current_price, config)` → `(PositionState, Optional[TradeAuditEntry])` — pure logic, no MT5 calls
- `_apply_sl_modification(ticket_id, new_sl, tp_price)` → `(bool, str)` — MT5 SLTP order, retry once on failure
- `apply_partial_close(position, config, order_manager)` → `(PositionState, list[TradeAuditEntry])` — executes TP1 partial close + breakeven SL
- `reconcile_positions(engine_positions)` → `(dict, list[TradeAuditEntry])` — prune externally closed
- `manage_positions(engine_positions, current_prices, config, order_manager)` → `(dict, list[TradeAuditEntry])` — main bar-level entry point

### `src/execution/execution_engine.py`
- `ExecutionEngine.__init__(order_manager, config, kill_switch_path)` — initialises `self._positions: dict[int, PositionState]`
- `execute_signal(exec_signal, day_start_equity, current_equity)` → `TradeAuditEntry` — full placement flow; never raises
- `manage_open_positions(current_prices)` → `list[TradeAuditEntry]` — bar-level position management
- `open_positions` property — read-only view for monitoring/tests

### `src/execution/__init__.py`
Exports: `ExecutionEngine`, `ExecutionSignal`, `PositionState`, `TradeAuditEntry`, `AuditAction`, `activate_kill_switch`, `deactivate_kill_switch`, `is_kill_switch_active`

---

## Config Updates (`config.yaml`)

```yaml
execution:
  trailing:
    activation_distance: 30.0     # Price units above/below entry to start trailing
    trailing_distance: 20.0       # SL kept this many price units behind price
  partial_close:
    tp1_close_ratio: 0.5          # 50% partial close at TP1
  magic_number: 20250519
  slippage_points: 5
  kill_switch_path: "logs/kill_switch.json"
  audit_log_path: "logs/trades.json"
```

---

## Test Strategy

### Unit Tests (no MT5 connection required — mock via pytest-mock)

| File | Requirements Covered |
|------|---------------------|
| `test_execution_models.py` | Entity instantiation, invariants, `AuditAction` completeness |
| `test_execution_kill_switch.py` | activate/deactivate/is_active, file absent = False, atomic write |
| `test_execution_preflight.py` | All 5 checks individually; `run_preflight` short-circuit order (D-006); all US1 acceptance scenarios (drawdown, margin, min-stop, kill-switch) |
| `test_execution_position_manager.py` | Trailing stop unidirectional (FR-009); TP1 partial close + breakeven SL (FR-011, FR-012); TP2 full close; reconcile stale position (FR-013); broker rejection retry (US2 S4) |
| `test_execution_audit_logger.py` | All AuditAction types produce entries; write failure does not raise (FR-018); concurrent writes do not corrupt log |
| `test_execution_engine.py` | execute_signal happy path; kill-switch blocks new entry while position managed (US4 S2); end-to-end mock round-trip |

### Integration Test (MT5 demo account)

`tests/integration/test_execution_integration.py`:
- Full round-trip: place → trail → partial close at TP1 → full close at TP2 (SC-008)
- Confirm audit log has one entry per action (SC-006)
- Confirm order placed has SL set at entry time (SC-001)

### Coverage Target
≥ 80% for all `src/execution/` modules (SC-007)

---

## Phased Delivery

```
Phase 1: models.py               — enums + dataclasses (no deps; required by all other modules)
Phase 2: kill_switch.py + tests  — atomic file I/O; operator safety mechanism (P1)
Phase 3: audit_logger.py + tests — thread-safe JSON append; write-failure isolation (P1)
Phase 4: preflight.py + tests    — all 5 pre-flight checks; run_preflight orchestrator (P1)
Phase 5: position_manager.py + tests — trailing stop, partial close, reconcile (P2)
Phase 6: execution_engine.py + tests — orchestrator; ties all modules together
Phase 7: integration test + config.yaml update + __init__.py + coverage check
```

---

## Risks & Follow-ups

- **MT5 minimum stop distance varies by broker** — `symbol_info.trade_stops_level` must be queried live; never hardcode. Covered by `check_minimum_stop_distance()` (FR-007).
- **Partial close lot rounding** — XAUUSD minimum lot step is 0.01; `round(lots, 2)` must be applied before broker submission to avoid `TRADE_RETCODE_INVALID_VOLUME` error.
- **`logs/trades.json` thread-safety overlap with spec001's `OrderManager._log_lock`** — both modules write to the same file. `audit_logger.py` must use the same lock instance, or the two modules must be refactored to share a single log writer. Mitigation: `audit_logger.py` owns a module-level lock and `OrderManager._log_trade()` is phased out in favour of `audit_logger.write_audit_entry()` (tracked as a task).
