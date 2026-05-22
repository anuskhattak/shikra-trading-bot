# Feature Specification: Execution Engine

**Feature Branch**: `005-execution-engine`
**Created**: 2026-05-19
**Status**: Implementation Complete
**Asset**: XAUUSD only
**Depends On**: 001-mt5-broker (order placement, position queries), 002-smc-engine (EntrySignal), 003-risk-management (RiskCalculation), 004-session-filters (SessionGate)

---

## Overview

The Execution Engine is the final stage of the Shikra trading pipeline. It receives a validated entry signal with a fully-computed risk calculation, performs pre-flight safety checks, places a market order with stop loss and take profit, and then actively manages the open position through its full lifecycle — including trailing stop adjustment, partial closure at the first profit target, and full closure at the second profit target or stop loss.

Every order action — placement, modification, partial close, full close, or rejection — is logged in a structured audit trail so that every trade decision is fully explainable.

---

## Clarifications

*(To be resolved via `/sp.clarify` if needed — see [NEEDS CLARIFICATION] markers in requirements)*

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Order Placement with SL and TP (Priority: P1)

The system places a XAUUSD market order with stop loss and take profit set at the time of entry, using the lot size and price levels calculated by the Risk Management module, only after all pre-flight checks pass.

**Why this priority**: Placing an order without a stop loss, or with incorrect sizing, is the most dangerous failure mode. This story is the irreducible core of the execution engine and must work perfectly before anything else.

**Independent Test**: Can be fully tested by supplying a synthetic validated signal + risk calculation and verifying that one market order with correct SL and TP appears in the broker's order history, and a corresponding audit log entry is created.

**Acceptance Scenarios**:

1. **Given** a validated entry signal and a computed risk calculation (lot size, SL price, TP1, TP2), **When** the execution engine receives them and all pre-flight checks pass, **Then** a market order is placed with SL = sl_price and TP = tp2_price before the confirmation is returned.
2. **Given** the daily drawdown limit has been reached, **When** a new signal arrives, **Then** the order is rejected, the rejection is logged with reason "daily drawdown limit reached", and no order is sent to the broker.
3. **Given** available margin on the account is insufficient for the calculated lot size, **When** the pre-flight check runs, **Then** the order is rejected and logged with reason "insufficient margin".
4. **Given** the SL distance is below the broker's minimum stop distance, **When** the pre-flight check runs, **Then** the order is rejected and logged with reason "SL distance below minimum".
5. **Given** the broker connection is unavailable at order submission time, **When** the engine attempts to place the order, **Then** the failure is logged and no partial order state is left open.

---

### User Story 2 — Trailing Stop Management (Priority: P2)

As price moves favorably after entry, the stop loss is automatically adjusted to lock in profits, reducing the risk of giving back unrealised gains.

**Why this priority**: Trailing stop is the primary mechanism for protecting open profits without requiring manual intervention. Without it, winning trades can turn into losers.

**Independent Test**: Can be tested by simulating price advancing past the trailing activation threshold and verifying that the broker-side SL is updated to the new trailing level, with an audit entry for the modification.

**Acceptance Scenarios**:

1. **Given** an open long position and price advances by a configurable trailing activation distance above entry, **When** the position manager evaluates the position, **Then** the stop loss is moved up to `current_price − trailing_distance` and the modification is logged. For SHORT positions the logic is symmetric: trailing activates when price declines by `activation_distance` below entry; the SL is moved down to `current_price + trailing_distance`.
2. **Given** the trailing stop has already been moved, **When** price advances further, **Then** the SL continues to follow price upward — it never moves backward.
3. **Given** price retraces without triggering the new SL, **When** the position manager evaluates, **Then** the SL remains at its last trailed level — it is not moved down.
4. **Given** the broker rejects the SL modification, **When** the engine receives the rejection, **Then** the failure is logged and the engine retries once before raising an alert.

---

### User Story 3 — Partial Close at First Profit Target (Priority: P2)

When price reaches the first take profit level (TP1), a configurable portion of the position is closed to bank partial profit, and the stop loss is moved to the entry price (breakeven) for the remaining position.

**Why this priority**: Partial close at TP1 + breakeven SL converts a risk trade into a free-ride, improving the system's risk-adjusted returns over time.

**Independent Test**: Can be tested by simulating price reaching TP1 and verifying that the partial close volume matches the configured ratio, the remaining position is still open, and SL has been updated to entry price.

**Acceptance Scenarios**:

1. **Given** an open position and price reaches TP1, **When** the partial close is triggered, **Then** the configured fraction of the position (e.g., 50%) is closed at market and a partial-close audit entry is created.
2. **Given** the partial close succeeds, **When** the remaining position is evaluated, **Then** the stop loss for the remaining position has been moved to the original entry price (breakeven).
3. **Given** the partial close order fails at the broker, **When** the error is received, **Then** the original full position remains intact, the failure is logged, and the trailing stop continues to manage the full position.
4. **Given** price reaches TP2 after a successful partial close, **When** the remaining position is evaluated, **Then** the remaining portion is fully closed and logged as the final exit.

---

### User Story 4 — Kill-Switch (Priority: P1)

An operator can immediately halt all new order placement system-wide, while allowing existing open positions to continue being managed normally.

**Why this priority**: The kill-switch is a safety mechanism that must work reliably. In an emergency (runaway losses, connection issues, unexpected market events), the operator must be able to stop the system from opening any new positions without affecting existing ones.

**Independent Test**: Can be tested by activating the kill-switch flag and verifying that a subsequent validated signal results in a logged rejection with reason "kill-switch active", while an already-open position continues to receive trailing stop updates.

**Acceptance Scenarios**:

1. **Given** the kill-switch is activated, **When** a new validated entry signal arrives, **Then** the order is rejected immediately, logged with reason "kill-switch active", and no broker call is made.
2. **Given** the kill-switch is active and an existing position is open, **When** trailing stop or partial-close conditions are met, **Then** position management continues normally — the kill-switch only blocks new entries.
3. **Given** the kill-switch is deactivated, **When** the next valid signal arrives, **Then** normal order placement resumes.

---

### User Story 5 — Full Trade Audit Trail (Priority: P1)

Every action taken by the execution engine — order placement, SL/TP modification, partial close, full close, and every rejection — produces a structured log entry that is persisted to disk.

**Why this priority**: Full auditability is a core system guarantee (CLAUDE.md). Without it, there is no way to diagnose misfires, explain regulatory queries, or backtest execution quality.

**Independent Test**: Can be tested by running a complete simulated trade cycle and verifying that the audit log file contains one entry per action with all required fields populated and no missing records.

**Acceptance Scenarios**:

1. **Given** any order action occurs (open, close, modify, reject), **When** it completes or is rejected, **Then** an audit log entry is written containing: timestamp (UTC), action type, ticket ID, lot size, entry price, SL price, TP prices, exit price (if applicable), P&L (if applicable), and reason.
2. **Given** the audit log file write fails (e.g., disk full), **When** the write error is caught, **Then** the error is reported to stderr but the trade action itself is not blocked.
3. **Given** the system restarts mid-session, **When** it recovers existing open positions, **Then** previously written audit entries are preserved and new entries are appended. This is satisfied by always opening `logs/trades.json` in append mode (`'a'`) — the file is never truncated or overwritten. Note: in-memory position flags (`trailing_activated`, `partial_close_done`) are not persisted and will be re-evaluated from scratch on restart (see Known Limitations §1).

---

### Edge Cases

- Signal arrives while a position for the same direction is already open — second entry must be rejected to prevent unintended pyramiding (FR-006 handles this).
- Two `execute_signal()` calls arrive in rapid succession for opposite directions — each direction is tracked independently; the pyramiding guard allows one LONG and one SHORT concurrently but rejects a second LONG while a LONG is already open. True thread-safety (lock-per-direction) is out of scope for Phase 1.
- Trailing stop update is triggered but position was already closed on the broker side (e.g., SL hit between polling intervals) — stale position must be detected and cleaned up without raising a false error.
- Partial close attempts to close more lots than are currently open (e.g., after manual intervention on MT5 terminal) — the engine must detect the lot mismatch, clamp `close_lots = position.lot_size`, log a warning, and not crash.
- TP2 is hit at the same bar as the trailing stop modification — only one close action must result; duplicate close attempts must be guarded against.
- Broker returns a filled order ticket but with a different fill price than requested (slippage) — audit log must record the actual fill price, not the requested price.

---

## Requirements *(mandatory)*

### Functional Requirements

**Order Placement**

- **FR-001**: The engine MUST accept a combined input of a validated `EntrySignal` and a computed `RiskCalculation`, and place a market order only when all pre-flight checks pass.
- **FR-002**: Stop loss and take profit (TP2 as primary exit) MUST be submitted as part of the order at placement time — they MUST NOT be set in a separate step after entry.
- **FR-003**: The engine MUST verify available account margin before placing any order; orders that would cause a margin call MUST be rejected. The margin check uses `mt5.order_calc_margin()` to compute the required margin for the requested lot size; the order is rejected when `account.margin_free < required_margin`.
- **FR-004**: The engine MUST reject order placement when the daily drawdown limit (from spec003 Risk Management) has been reached for the current trading day.
- **FR-005**: The engine MUST reject order placement when the kill-switch flag is active.
- **FR-006**: The engine MUST reject order placement if an open position in the same direction already exists (no pyramiding).
- **FR-007**: The engine MUST validate that the SL distance in price units meets or exceeds the broker's minimum stop distance before submission.

**Position Management**

- **FR-008**: The engine MUST monitor all open positions and evaluate trailing stop conditions on each new H1 price bar (configurable via Assumption §5; default period is H1).
- **FR-009**: The trailing stop MUST be unidirectional — it moves only in the direction of the trade and never reverses.
- **FR-010**: The trailing stop activation threshold and trailing distance MUST be configurable parameters, not hardcoded values. These values MUST be validated on engine initialization: `activation_distance > 0.0`, `trailing_distance > 0.0`, `tp1_close_ratio ∈ (0.0, 1.0)` exclusive. Invalid values MUST raise a `ValueError` at startup.
- **FR-011**: The engine MUST trigger a partial close when price reaches TP1, closing a configurable fraction of the position (default: 50%).
- **FR-012**: After a successful partial close, the engine MUST move the remaining position's stop loss to the original entry price (breakeven).
- **FR-013**: The engine MUST detect when a position has been closed externally (e.g., SL hit, manual close) and remove it from active position tracking without error.

**Kill-Switch & Safety**

- **FR-014**: The kill-switch MUST be activatable without restarting the bot process — it MUST be readable from a runtime-writable file-based state store only (temp-file + atomic rename pattern; no in-memory flag). A missing or malformed state file MUST be treated as inactive (fail-safe default).
- **FR-015**: Kill-switch activation MUST take effect within one evaluation cycle (one price bar) of being set.

**Audit Logging**

- **FR-016**: Every order action (placement, rejection, SL/TP modification, partial close, full close) MUST produce a structured log entry written to `logs/trades.json`. If the file does not exist, it MUST be created on the first write. All subsequent writes MUST append — the file MUST NOT be truncated or overwritten. Field population in `TradeAuditEntry` is the caller's responsibility; no factory functions are provided.
- **FR-017**: Each audit log entry MUST include: UTC timestamp, action type, broker ticket ID, direction, lot size, requested entry price, actual fill price, SL price, TP1 price, TP2 price, exit price (if applicable), realised P&L (if applicable), rejection reason (if applicable), maximum loss in USD at entry (if applicable), entry reason — the SMC pattern that triggered the signal (if applicable), and exit reason (if applicable).
- **FR-018**: Audit log write failures MUST NOT block or abort trade actions.

### Key Entities

- **ExecutionSignal**: Composite input to the engine — contains the validated `EntrySignal` (direction, entry price, confidence score) and `RiskCalculation` (lot size, sl_price, tp1_price, tp2_price) from spec002 and spec003 respectively.
- **OrderTicket**: Broker-assigned record of a placed order — ticket ID, direction, lot size, entry price, current SL/TP, open time, current status (open/closed/pending).
- **PositionState**: Engine's in-memory view of an open position — entry price, current SL, trailing activation status, partial-close status, running P&L.
- **TradeAuditEntry**: Immutable record of a single order action — all fields from FR-017; appended to `logs/trades.json`.
- **KillSwitchState**: Binary flag (active/inactive) readable by all engine components; when active, blocks all new order placement.

---

## Assumptions

1. Only market orders are used in Phase 1 — limit and stop-entry orders are out of scope.
2. The engine manages at most one position per direction at any time (no pyramiding).
3. Lot size, SL price, and TP prices are always provided by the Risk Management module (spec003) — the execution engine does not recalculate them independently. `RiskCalculation.lot_size` is guaranteed to be > 0.0 by spec003 at calculation time; the execution engine does not re-validate this constraint.
4. Session gate checks are performed upstream by spec004 filters before the signal reaches the execution engine — the engine does not re-check session windows. This is a mandatory pre-condition: calling code (the orchestrator) MUST apply spec004 session filtering before passing a signal to `execute_signal()`.
5. The broker polling interval (for position state updates) is one H1 bar by default; this is a configuration parameter.
6. Slippage is accepted silently — the engine records the actual fill price in the audit log but does not retry on slippage.
7. XAUUSD only — no multi-symbol position tracking.
8. **Windows-only deployment**: MetaTrader 5 Python API (`MetaTrader5` package) is Windows-only. The execution engine has a hard runtime dependency on Windows and cannot run on Linux or macOS.
9. **Magic number isolation**: Each running bot instance MUST use a unique `magic_number` (configured in `config.yaml → execution.magic_number`) to prevent order cross-contamination when multiple instances connect to the same MT5 account. Default: `202605` (must be changed for parallel deployments).

---

## Dependencies

| Spec | Module | What It Provides |
|------|--------|-----------------|
| 001-mt5-broker | `order_manager.py` | Place order, modify SL/TP, close position, query open positions |
| 002-smc-engine | Signal models | `EntrySignal` data structure |
| 003-risk-management | Risk models | `RiskCalculation` data structure (lot size, sl_price, tp1, tp2) |
| 004-session-filters | Filter pipeline | Session gate — signals that reach execution engine are already session-validated |

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every placed order has a stop loss set at entry time — 0 orders exist in broker history without a stop loss.
- **SC-002**: Orders are placed (or rejected) within 3 seconds of receiving a validated entry signal. Measurement: mean latency under normal load (single sequential signal, no concurrent execution). Start boundary: signal received at `execute_signal()` entry point. End boundary: `TradeAuditEntry` returned to caller.
- **SC-003**: Trailing stop adjustments are applied within one H1 price bar of the trailing activation condition being met.
- **SC-004**: Partial close executes within one H1 price bar of price reaching TP1.
- **SC-005**: Kill-switch halts all new order placement within one evaluation cycle (≤ 60 seconds) of activation.
- **SC-006**: 100% of order actions have a corresponding audit log entry — no silent executions.
- **SC-007**: Aggregate line coverage ≥ 80% for `src/execution/` (all modules combined). Branch coverage is not a gate requirement; line coverage is. Measured via `pytest --cov=src/execution`.
- **SC-008**: Integration test confirms a complete round-trip trade cycle (place → trail → partial close → full close) on an MT5 demo account without manual intervention.
- **SC-009**: No order is placed that would trigger a margin call — margin check rejects 100% of such signals in test. Threshold: `account.margin_free < mt5.order_calc_margin(symbol, lot_size)`. A zero or negative free-margin scenario is the required test condition.

---

## Known Limitations

1. **In-memory position flags are not persisted**: `trailing_activated` and `partial_close_done` flags are stored in `PositionState` objects in memory only. If the process restarts mid-session, these flags reset to `False` and the engine re-evaluates trailing/partial-close from scratch. Operators must be aware that a restart on an open position may cause a second partial close if price is still above TP1.

2. **No true thread safety for concurrent signals**: The pyramiding guard (FR-006) prevents duplicate positions per direction via the in-memory `_positions` dict, but this guard is not protected by a lock. Concurrent calls to `execute_signal()` from multiple threads are not supported in Phase 1.

3. **Kill-switch atomicity is not fully verifiable in unit tests**: The temp-file + atomic rename pattern guarantees atomic writes on the OS level, but a unit test cannot simulate a mid-rename process kill. The observable guarantee is: `is_kill_switch_active()` returns `False` when the state file is absent or malformed (fail-safe default), and the integration test verifies end-to-end activation behavior.

---

## Delivery Gates

Before any live (non-demo) account connection, ALL of the following gates must be cleared:

1. **Unit & Integration Tests**: All unit tests pass with ≥ 80% aggregate line coverage on `src/execution/`. All mocked integration tests pass. (SC-007, SC-008)
2. **MT5 Demo Paper Trading**: Successful execution on a demo MT5 account with no manual intervention for a minimum of 1 week. (CLAUDE.md §Quality Gates §3)
3. **Backtesting Gate**: Backtest results show win rate ≥ 50%, profit factor ≥ 1.5, max drawdown < 30% on minimum 2 years of XAUUSD data. (CLAUDE.md §Quality Gates)
4. **Senior Architect Review**: A senior architect must manually review and approve the full execution pipeline before live account credentials are used. This gate applies after SC-008 integration test passes and before any live order is placed. (CLAUDE.md §Quality Gates §4)
5. **Kill-Switch Armed**: The kill-switch mechanism must be tested and confirmed functional before live trading begins. Emergency stop must be verified to halt trading within one evaluation cycle.
