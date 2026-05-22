---
id: PHR-0038
title: Execution Engine ADRs Created
stage: plan
date: 2026-05-20
surface: claude-code
model: claude-sonnet-4-6
feature: 005-execution-engine
branch: 005-execution-engine
user: anaskhattak
command: /sp.adr
labels: [adr, execution-engine, spec005, architecture]
links:
  spec: specs/005-execution-engine/spec.md
  ticket: N/A
  adr: history/adr/ADR-0001, ADR-0002, ADR-0003, ADR-0004
  pr: N/A
files:
  - history/adr/ADR-0001-kill-switch-safety-mechanism.md
  - history/adr/ADR-0002-position-state-ownership-and-polling.md
  - history/adr/ADR-0003-trade-audit-trail-design.md
  - history/adr/ADR-0004-order-execution-and-position-lifecycle-pattern.md
tests: []
---

## Prompt

/sp.adr — Analyze planning artifacts for spec005 (Execution Engine) and document architecturally significant decisions as ADRs.

## Response snapshot

Extracted 4 architectural decision clusters from plan.md and research.md. All 4 passed significance test (long-term impact + alternatives considered + cross-cutting scope). Zero existing ADRs found in history/adr/. Created 4 new ADRs:

- **ADR-0001**: Kill-Switch Safety Mechanism — file-based `logs/kill_switch.json`, atomic write, no restart required (D-001). Alternatives: in-memory flag, SQLite, OS process signal, env var.
- **ADR-0002**: Position State Ownership & Polling — engine-side dict, synchronous H1 bar loop, per-bar reconciliation via `mt5.positions_get()` (D-002, D-005, D-009). Alternatives: JSON persistence, asyncio, tick polling, MT5 callbacks.
- **ADR-0003**: Trade Audit Trail Design — standalone `TradeAuditEntry` dataclass (not extending `TradeOrder`), single `logs/trades.json` with one lock, `AuditAction` enum, write-failure isolation (D-004). Alternatives: inheritance, two log files, loguru JSON sink, SQLite.
- **ADR-0004**: Order Execution & Position Lifecycle Pattern — composite `ExecutionSignal`, cheapest-first pre-flight order, counter-direction `order_send` for partial close, exact-entry-price breakeven (D-003, D-006, D-007, D-008). Alternatives: flattened signal, no short-circuit, full-close-reenter, buffered breakeven.

## Outcome

- ✅ Impact: Complete architectural record for spec005 — all significant decisions documented with rationale and alternatives
- 🧪 Tests: N/A — ADR creation task; no code tests
- 📁 Files: 4 ADR files created in `history/adr/`
- 🔁 Next prompts: `/sp.tasks` to generate `tasks.md` for spec005 implementation
- 🧠 Reflection: ADR-0003 surfaces the most critical cross-spec risk — dual lock on `logs/trades.json` between spec001 (`OrderManager._log_lock`) and spec005 (`audit_logger.py`). This must be resolved in the first implementation task before any writes to trades.json from the execution engine.

## Evaluation notes (flywheel)

- Failure modes observed: None — all 4 clusters clearly distinct and independently significant
- Graders run and results (PASS/FAIL): All 4 ADRs PASS significance checklist (impact + alternatives + cross-cutting)
- Prompt variant (if applicable): N/A
- Next experiment: Consider whether ADR-0002's "restart loses trailing_activated flag" limitation warrants a lightweight state persistence follow-up ADR once the implementation is proven
