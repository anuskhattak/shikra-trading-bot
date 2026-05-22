# ADR-0004: Order Execution and Position Lifecycle Pattern

- **Status:** Accepted
- **Date:** 2026-05-20
- **Feature:** 005-execution-engine
- **Context:** The execution engine is the final stage of the Shikra pipeline. It must: (1) accept a combined input from spec002 (EntrySignal) and spec003 (RiskCalculation), (2) run 5 pre-flight safety checks before any broker call, (3) place a market order with mandatory SL+TP, (4) partially close at TP1 and move SL to breakeven, and (5) trail the stop loss as price moves favorably. Each of these sub-problems has non-obvious design choices with significant tradeoffs. They are grouped here because they define the complete execution lifecycle and would change together if the approach changes.

## Decision

**Four integrated pattern decisions that define the full order lifecycle:**

### 1. ExecutionSignal — Composite Dataclass (Not Flattened)
`ExecutionSignal` wraps `entry_signal: EntrySignal` and `risk_calc: RiskCalculation` as named fields. Callers access `exec_signal.entry_signal.direction` and `exec_signal.risk_calc.lot_size` — provenance is always traceable.

### 2. Pre-Flight Check Order — Cheapest-First with Short-Circuit
Checks run in this fixed order, short-circuiting on first failure:
1. Kill-switch active (in-memory read — O(1))
2. Existing same-direction position (dict lookup — O(n positions))
3. Daily drawdown (delegates to spec003 `check_drawdown()` — arithmetic)
4. Margin sufficiency (`mt5.order_check()` — network call)
5. Minimum stop distance (`mt5.symbol_info()` — network call)
MT5 API calls are last because they carry network latency; the two cheapest checks eliminate the majority of blocked signals before touching the broker.

### 3. Partial Close via Counter-Direction `order_send` with `position=ticket_id`
MT5 has no `TRADE_ACTION_CLOSE_PARTIAL` action type. Partial close is implemented as a new `TRADE_ACTION_DEAL` in the opposite direction with `"position": ticket_id` set in the request dict, volume = `lot_size × tp1_close_ratio`. MT5 natively nets this against the open position when the `position` field is provided.

### 4. Breakeven SL = Entry Price Exactly (No Buffer)
After a successful partial close at TP1, the remaining position's stop loss is moved to the original `entry_price` via `TRADE_ACTION_SLTP`. No pip buffer is added. The broker's minimum stop distance is validated before the modification (same check as pre-flight step 5).

## Consequences

### Positive

- `ExecutionSignal` composite preserves full audit context — `signal_id`, direction, confidence, and risk params are all available in one object for both the pre-flight check and the audit logger
- Cheapest-first pre-flight order means kill-switch and pyramiding checks (the most common rejection causes) never trigger MT5 network calls
- Counter-direction `order_send` with `position` parameter is the only officially supported MT5 partial close mechanism — using it avoids undocumented API behaviour
- Breakeven at exact entry price is the universally understood "free ride" mechanic — no ambiguity about what "breakeven" means in the audit log or for the operator

### Negative

- `ExecutionSignal` with two nested objects means callers must know to check `exec_signal.risk_calc.lot_size > 0` before passing to the engine — a zero-lot signal from spec003 must never reach the execution engine
- Mitigation: `ExecutionEngine.execute_signal()` asserts `lot_size > 0` as a precondition and raises `ValueError` (fail-fast, not silent)
- Counter-direction partial close creates two trades in the MT5 history (the original and the partial close order) — reconciling full-lifecycle P&L from history requires joining both records by ticket ID
- Mitigation: `TradeAuditEntry` for PARTIAL_CLOSE records the original `ticket_id` and the partial close's `audit_id`, enabling programmatic join
- Breakeven SL with no buffer means the remaining position may be stopped out on a spread spike at the exact entry price — no protection against broker noise at the entry level
- Mitigation: This is an accepted tradeoff (industry-standard breakeven mechanic); operators may adjust `entry_price` ± a buffer via config in a future enhancement

## Alternatives Considered

**Alternative for ExecutionSignal: Flattened dataclass with all 15 fields from EntrySignal + RiskCalculation merged**
- One flat struct: `direction`, `confidence`, `lot_size`, `sl_price`, `tp1_price`, `tp2_price`, `entry_zone_top`, etc.
- Rejected: `reason` field exists in both `EntrySignal` and `RiskCalculation` with different semantics — flattening causes collision. Provenance (which spec produced which value) is lost. Future changes to either upstream model require updating the flattened struct.

**Alternative for Pre-Flight Order: Fixed alphabetical / arbitrary order**
- Checks run in any order; all 5 always run (no short-circuit)
- Rejected: Running all 5 checks including two MT5 API calls for every signal that should be blocked by the kill-switch is wasteful and increases latency beyond SC-002's 3-second window under high signal load.

**Alternative for Partial Close: Close full position and re-enter with reduced lot size**
- Close 100% of position at TP1, immediately re-enter a new market order for `lot_size × (1 - tp1_close_ratio)`
- Rejected: Two separate orders create a gap in the position during re-entry (spread cost × 2, timing risk, potential re-entry failure). The re-entry constitutes a new signal requiring a new pre-flight check. The new order would have a different ticket ID, breaking audit continuity. Not viable.

**Alternative for Breakeven SL: Entry price + N pips buffer**
- Move SL to `entry_price + buffer_pips` (e.g., +5 pips) to absorb spread noise
- Rejected: The buffer value would be broker/account-specific and requires a new config parameter. Spec FR-012 states "entry price (breakeven)" without a buffer. The operator can manually adjust the SL after partial close if they want a buffer — this is outside the engine's automated scope.

## References

- Feature Spec: specs/005-execution-engine/spec.md (FR-001–FR-007, FR-011, FR-012, US1, US3)
- Implementation Plan: specs/005-execution-engine/plan.md (D-003, D-006, D-007, D-008)
- Research: specs/005-execution-engine/research.md (D-003, D-006, D-007, D-008)
- Related ADRs: ADR-0003 (Trade Audit Trail Design — partial close audit entry format)
- Evaluator Evidence: history/prompts/005-execution-engine/PHR-0037-execution-engine-plan-generated.md
