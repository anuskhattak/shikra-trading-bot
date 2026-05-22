# ADR-0002: Position State Ownership and Polling Architecture

- **Status:** Accepted
- **Date:** 2026-05-20
- **Feature:** 005-execution-engine
- **Context:** The execution engine must monitor all open XAUUSD positions on each H1 bar to apply trailing stop adjustments, detect TP1/TP2 hits, and detect external closes (SL hit, manual close from MT5 terminal). MT5's Python SDK is synchronous-only and not thread-safe — all `mt5.*` calls must originate from the same thread. The system must handle positions that were closed externally between polling intervals without raising errors or leaving stale state.

## Decision

**Engine-side in-memory `dict[int, PositionState]` with per-bar reconciliation:**

- **Ownership**: `ExecutionEngine` holds `self._positions: dict[int, PositionState]` keyed by MT5 ticket ID
- **What the dict stores**: Derived state the broker does not persist — `trailing_activated`, `partial_close_done`, original `entry_price`, `signal_id` for audit correlation
- **Polling cadence**: `manage_open_positions()` called synchronously by the main loop on each H1 bar close — same cadence as the SMC engine (spec002)
- **Reconciliation**: On each bar, `reconcile_positions()` calls `mt5.positions_get(symbol="XAUUSD")`; any ticket ID in the engine dict not present in the broker response is treated as externally closed — a `POSITION_EXTERNALLY_CLOSED` audit entry is written and the ticket is removed
- **Threading**: No threads or async inside the execution engine; all MT5 calls remain on the main thread
- **State authority**: MT5 is authoritative for price, volume, and open/closed status; the engine dict is authoritative for derived tracking state only

## Consequences

### Positive

- No threading complexity or MT5 thread-safety violations — the entire engine runs on the main event loop thread
- Reconciliation catches all external closes (SL hit, manual close, margin call) without needing MT5 callbacks or push events
- Engine dict is thin (derived state only) — no duplication of MT5 fields reduces inconsistency risk
- H1 cadence aligns with the strategy's timeframe: trailing stop and partial close accuracy within one bar is acceptable per spec (SC-003, SC-004)
- Simple restart recovery: on restart, `reconcile_positions()` immediately rebuilds state from `mt5.positions_get()` (partial — trailing activation history is lost, but position continuity is preserved)

### Negative

- Trailing activation history (`trailing_activated`, `partial_close_done`) is lost on process restart — if the bot restarts mid-position, these flags are reset to False, and the trailing stop may not re-activate until the trailing threshold is re-crossed
- Mitigation: On restart, existing positions are detected via reconciliation and re-entered into the dict; however, the `partial_close_done` flag will be False even if partial close already happened. This is a documented limitation: the operator must verify manually after restart
- H1 polling means a position that hits TP2 intrabar and reverses will be closed at the next bar's evaluation, not at the exact TP2 candle — acceptable for H1 strategy, unacceptable for lower timeframes

## Alternatives Considered

**Alternative A: Persistent PositionState to JSON file**
- Serialize `self._positions` to `logs/position_state.json` after every update
- Rejected: Adds a write on every bar update. MT5 is authoritative anyway; the value of persisting derived state (trailing_activated, partial_close_done) does not justify the write overhead and file-consistency complexity. Restarts are rare enough that manual verification is acceptable

**Alternative B: asyncio event loop with MT5 adapter**
- Wrap MT5 calls in `asyncio.run_in_executor()` for async position monitoring
- Rejected: MT5 Python SDK is synchronous and not documented as thread-safe. All documented MT5 Python examples use single-threaded polling. Introducing threading via executor risks silent data corruption on concurrent MT5 calls

**Alternative C: Tick-based polling (every N seconds)**
- Poll `mt5.positions_get()` every 5–10 seconds from a background thread
- Rejected: Violates MT5 thread-safety. Sub-bar resolution is unnecessary for an H1 strategy — the spec accepts "within one H1 bar" accuracy (SC-003). Adds complexity without benefit

**Alternative D: MT5 event callbacks (if available)**
- Use MT5 position-change callbacks to receive push notifications
- Rejected: MT5 Python SDK does not expose event callbacks — only polling via `positions_get()`, `orders_get()`, and `history_deals_get()` is available

## References

- Feature Spec: specs/005-execution-engine/spec.md (FR-008, FR-013, SC-003, SC-004)
- Implementation Plan: specs/005-execution-engine/plan.md (D-002, D-005, D-009)
- Research: specs/005-execution-engine/research.md (D-002, D-005, D-009)
- Related ADRs: None
- Evaluator Evidence: history/prompts/005-execution-engine/PHR-0037-execution-engine-plan-generated.md
