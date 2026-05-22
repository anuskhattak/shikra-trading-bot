# Research: Execution Engine (spec005)

**Branch**: `005-execution-engine` | **Date**: 2026-05-20  
**Phase**: 0 — All NEEDS CLARIFICATION resolved before design

---

## D-001: Kill-Switch Implementation — File-Based Flag

**Decision**: Kill-switch state is stored in `logs/kill_switch.json` (`{"active": true/false}`). On each evaluation cycle the engine reads this file; an in-memory cache is updated. A helper function `set_kill_switch(active: bool)` writes the file atomically.

**Rationale**: FR-014 requires the kill-switch to be activatable **without restarting the process**. A file-based flag allows an operator to write `{"active": true}` from a terminal, another script, or a monitoring dashboard without any IPC or socket setup. Python's `pathlib.Path.write_text` with a temp-file-then-rename pattern provides atomic writes on Windows. An in-memory bool is checked first per cycle (avoids repeated disk reads on the hot path); the file is the durable source of truth across restarts.

**Alternatives Considered**:
- *Pure in-memory flag*: Fast but lost on process restart — violates FR-014 durable state requirement.
- *Database row / Redis*: Overkill for a single binary flag with no concurrent writers outside the operator.
- *Signal (SIGTERM/SIGUSR1)*: Not reliably cross-platform on Windows; MT5 runs on Windows.

---

## D-002: Position Polling — Synchronous H1 Bar Loop

**Decision**: `manage_positions()` is called synchronously by the main event loop on each new H1 OHLCV bar (same loop that drives the SMC engine). No threads or async I/O inside the execution engine itself.

**Rationale**: The SMC engine already polls on H1 bars (spec002). Aligning position management to the same cadence (SC-003: "within one H1 price bar") avoids threading complexity and race conditions on `PositionState`. MT5's Python API is not thread-safe; all MT5 calls must come from the same thread.

**Alternatives Considered**:
- *asyncio event loop*: Would require async wrappers around every MT5 call; MT5 SDK is synchronous-only.
- *Background thread polling every N seconds*: Introduces lock contention on `PositionState` and MT5 thread-safety violations.
- *Tick-based polling*: Sub-bar resolution is unnecessary for trailing stop management on H1 strategy.

---

## D-003: Partial Close via MT5 `order_send` with Reduced Volume

**Decision**: Partial close is implemented by sending a new counter-direction `TRADE_ACTION_DEAL` order with volume = `lot_size × partial_close_ratio`. This is the standard MT5 partial close pattern — MT5 does not have a dedicated partial-close action.

**Rationale**: MT5 API `mt5.order_send()` does not offer a `TRADE_ACTION_CLOSE_PARTIAL` type. The canonical approach is a market order in the opposite direction for the partial volume, which MT5 natively nets against the open position when `position` parameter is set to the ticket ID.

**Implementation Note**: The request dict must include `"position": ticket_id` so MT5 links the counter-order to the open position rather than opening a second position.

**Alternatives Considered**:
- *Close full position and re-enter remaining*: Creates a full audit break, higher spread cost, and timing risk on re-entry.
- *Pending stop-loss at TP1*: Would trigger a full close, not partial.

---

## D-004: `TradeAuditEntry` — Separate Dataclass, Not Extension of `TradeOrder`

**Decision**: `TradeAuditEntry` (spec005 models.py) is a new standalone dataclass. It does **not** inherit from `TradeOrder` (spec001 `order_manager.py`).

**Rationale**: `TradeOrder` in spec001 was designed for the narrow order-placement flow. `TradeAuditEntry` must cover: order open, SL modification, partial close, full close, and rejection — each requiring different fields (e.g., `exit_price`, `realised_pnl`, `action_type`). Inheritance would pollute `TradeOrder`'s interface with optional fields irrelevant to placement. Composition (the audit logger reads `TradeOrder` data and maps it into `TradeAuditEntry`) keeps the boundary clean.

**Alternatives Considered**:
- *Extend `TradeOrder` with Optional fields*: Fields like `exit_price` and `realised_pnl` are meaningless on an open-order record; Optional fields would require None-checks everywhere.
- *Reuse `TradeOrder` dict directly*: Loses type safety and makes FR-017 field requirements unenforceable at the type level.

---

## D-005: `PositionState` Ownership — Engine-Side In-Memory Dict

**Decision**: The execution engine maintains a `dict[int, PositionState]` keyed by MT5 ticket ID. On each bar, the engine calls `mt5.positions_get(symbol="XAUUSD")` and reconciles the live broker state against its in-memory dict.

**Rationale**: MT5 position queries are authoritative. The engine's dict is a cache of derived state (trailing status, partial-close flag, entry price at time of placement) that the broker does not store. Reconciliation on every bar handles external closes (SL hit, manual close) without keeping stale state (FR-013, edge case in spec).

**Alternatives Considered**:
- *Persist PositionState to JSON file*: Adds write latency on every bar update with minimal benefit — MT5 is authoritative anyway; the engine dict is rebuilt from broker state on restart.
- *Query MT5 on every tick*: Not needed for H1 strategy; excessive API calls.

---

## D-006: Pre-Flight Check Order — Kill-Switch → Pyramiding → Drawdown → Margin → Min-Stop

**Decision**: Pre-flight checks run in this order, short-circuiting on first failure:
1. Kill-switch active check (FR-005) — cheapest, no external call
2. Existing same-direction position check (FR-006) — in-memory dict lookup
3. Daily drawdown check (FR-004) — reuse `check_drawdown()` from spec003
4. Margin sufficiency check (FR-003) — MT5 `account_info()` call
5. Minimum stop distance check (FR-007) — MT5 `symbol_info()` call

**Rationale**: Cheapest checks first, most expensive (MT5 API calls) last. Kill-switch is O(1) memory read; MT5 API calls carry network latency. Short-circuit means failed kill-switch never hits the broker.

---

## D-007: `ExecutionSignal` — Composite Dataclass (not a Union or TypedDict)

**Decision**: `ExecutionSignal` is a Python `@dataclass` with two fields: `entry_signal: EntrySignal` and `risk_calc: RiskCalculation`. It does not flatten fields from both.

**Rationale**: Keeps provenance clear — callers can access `exec_signal.entry_signal.direction` and `exec_signal.risk_calc.lot_size` without ambiguity. Flattening would duplicate field names (both have `reason`) and create a monolithic struct with 15+ fields.

---

## D-008: Breakeven SL After Partial Close — Move to `entry_price` Exactly

**Decision**: After a successful partial close at TP1, the remaining position's stop loss is moved to the original `entry_price` (FR-012). The modification uses `mt5.order_send()` with `TRADE_ACTION_SLTP`.

**Rationale**: Breakeven exactly at entry is the industry-standard "free ride" mechanic — no slippage buffer is added. The broker's minimum stop distance is checked before the SLTP modification, same as FR-007 for the initial order.

---

## D-009: Stale Position Detection — Compare Engine Dict vs. Broker Positions

**Decision**: On each bar, if a ticket ID in the engine's `PositionState` dict is **not** returned by `mt5.positions_get()`, the position is considered externally closed. The engine logs a `POSITION_EXTERNALLY_CLOSED` audit entry and removes the ticket from its dict.

**Rationale**: FR-013 requires detecting external closes without error. Absence from `mt5.positions_get()` is the only reliable signal — there is no MT5 callback or event push for position closes.

---

## Resolved: No NEEDS CLARIFICATION Remaining

All unknowns from Technical Context are resolved above. Design can proceed.
