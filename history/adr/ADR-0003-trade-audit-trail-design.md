# ADR-0003: Trade Audit Trail Design

- **Status:** Accepted
- **Date:** 2026-05-20
- **Feature:** 005-execution-engine
- **Context:** Full auditability is a core system guarantee (CLAUDE.md §3): every trade action must produce a structured log entry. Two modules — `OrderManager` (spec001, `src/broker/order_manager.py`) and the Execution Engine (spec005) — both need to write to `logs/trades.json`. spec001 already has a `_log_lock` threading lock and a `TradeOrder` dataclass for placement records. spec005 needs to log 8 action types (ORDER_PLACED, ORDER_REJECTED, TRAILING_STOP_UPDATED, BREAKEVEN_SET, PARTIAL_CLOSE, FULL_CLOSE, SL_MODIFICATION_FAILED, POSITION_EXTERNALLY_CLOSED), each with different optional fields. The system must not block trade actions on audit log write failures (FR-018).

## Decision

**`TradeAuditEntry` is a standalone dataclass in `src/execution/models.py`; `audit_logger.py` owns the write responsibility for all spec005 events; `OrderManager._log_trade()` is phased out in a follow-up task and replaced by `audit_logger.write_audit_entry()`:**

- **Dataclass**: `TradeAuditEntry` — 19 fields, all Optional except `audit_id`, `timestamp_utc`, `action_type`, `signal_id`; captures all FR-017 fields
- **`AuditAction` enum**: 8 values covering the full position lifecycle (ORDER_PLACED through POSITION_EXTERNALLY_CLOSED)
- **Log file**: `logs/trades.json` — single file, append-only JSON array
- **Thread safety**: `audit_logger.py` owns a module-level `threading.Lock()` — same file, same lock — eliminating dual-lock risk once `OrderManager._log_trade()` is retired
- **Failure isolation**: `write_audit_entry()` swallows all write exceptions and logs to stderr; trade actions are never blocked (FR-018)
- **Not inheritance**: `TradeAuditEntry` does NOT extend `TradeOrder` from spec001

## Consequences

### Positive

- Single lock on `logs/trades.json` eliminates write interleaving between spec001 and spec005
- `AuditAction` enum makes all possible log event types explicit and exhaustive — impossible to forget a case
- Optional fields allow one dataclass to represent all 8 event types without subclassing
- `audit_logger.write_audit_entries(list)` batch form acquires lock once for multiple entries per bar (performance)
- Audit log is human-readable JSON — operators and analysts can inspect without tooling

### Negative

- Until `OrderManager._log_trade()` is retired (follow-up task), there is a window where both locks exist and could write to the same file concurrently, corrupting the JSON array
- Mitigation: This risk is explicitly tracked as a phased delivery task; spec005 integration test verifies no corruption before merge
- `TradeAuditEntry` has 19 fields, most Optional — callers must know which fields apply to which `AuditAction`, which is an implicit convention
- Mitigation: Factory functions in `audit_logger.py` (e.g., `make_order_placed_entry()`) enforce required fields per action type

## Alternatives Considered

**Alternative A: Extend `TradeOrder` (inheritance)**
- `TradeAuditEntry(TradeOrder)` adds `exit_price`, `realised_pnl`, `action_type` etc.
- Rejected: `TradeOrder` was designed for the single-use placement flow. Inheritance would add Optional fields (`exit_price`, `realised_pnl`) that are meaningless on an open-order record, and expose spec001's internals to spec005. Field name collision (`reason` exists in both models). Cross-spec inheritance creates tight coupling between modules that should be independently deployable/testable.

**Alternative B: Two separate log files (`trades.json` for placement, `position_events.json` for management)**
- `OrderManager` keeps `trades.json`; `audit_logger.py` writes to `position_events.json`
- Rejected: Splits the audit trail across two files, making it impossible to reconstruct a full trade lifecycle from one source. Analysts and the backtester would need to join two files on ticket ID. FR-016 specifies "written to `logs/trades.json`" (singular).

**Alternative C: Structured logging via loguru to a single log file**
- Use `loguru` with a JSON sink instead of a custom JSON array
- Rejected: `loguru` JSON output is line-delimited JSONL, not a JSON array — harder to parse with standard `json.load()`. The spec requires field-level structure (FR-017 lists 15 specific fields). Custom dataclass gives type-safe field enforcement that loguru string interpolation does not.

**Alternative D: Database (SQLite) for audit records**
- Each audit entry → INSERT into `trades` table
- Rejected: Adds SQLite dependency and schema migration overhead. The existing `logs/trades.json` pattern is established by spec001 and consistent with `logs/risk_events.json` (spec003) and `logs/filter_decisions.json` (spec004). Introducing a database mid-project would be an inconsistent architectural deviation.

## References

- Feature Spec: specs/005-execution-engine/spec.md (FR-016, FR-017, FR-018, US5)
- Implementation Plan: specs/005-execution-engine/plan.md (D-004, "Risks & Follow-ups")
- Research: specs/005-execution-engine/research.md (D-004)
- Related ADRs: None (but relates to spec001 OrderManager design)
- Evaluator Evidence: history/prompts/005-execution-engine/PHR-0037-execution-engine-plan-generated.md
