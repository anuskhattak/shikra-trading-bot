---
id: PHR-0037
title: Execution Engine Plan Generated
stage: plan
date: 2026-05-20
surface: claude-code
model: claude-sonnet-4-6
feature: 005-execution-engine
branch: 005-execution-engine
user: anaskhattak
command: /sp.plan
labels: [plan, execution-engine, spec005, trading-pipeline]
links:
  spec: specs/005-execution-engine/spec.md
  ticket: N/A
  adr: N/A
  pr: N/A
files:
  - specs/005-execution-engine/plan.md
  - specs/005-execution-engine/research.md
  - specs/005-execution-engine/data-model.md
  - specs/005-execution-engine/quickstart.md
  - specs/005-execution-engine/contracts/execution_engine.md
tests:
  - tests/unit/test_execution_preflight.py (planned)
  - tests/unit/test_execution_position_manager.py (planned)
  - tests/unit/test_execution_engine.py (planned)
  - tests/integration/test_execution_integration.py (planned)
---

## Prompt

spec005 ka /sp.plan banao

## Response snapshot

Generated complete implementation plan for the Execution Engine (spec005) — the final stage of the Shikra trading pipeline. Produced five design artifacts:

**Phase 0 — Research (`research.md`)**: Resolved 9 design decisions:
- D-001: Kill-switch via `logs/kill_switch.json` (file-based, atomic write, operator-accessible without restart)
- D-002: Position polling on H1 bar loop (synchronous; MT5 SDK not thread-safe)
- D-003: Partial close via counter-direction `order_send` with `position=ticket_id` (MT5 canonical pattern)
- D-004: `TradeAuditEntry` standalone dataclass (not extension of `TradeOrder`)
- D-005: `PositionState` dict reconciled per bar via `mt5.positions_get()`
- D-006: Pre-flight order: kill-switch → pyramiding → drawdown → margin → min-stop
- D-007: `ExecutionSignal` composite dataclass (not flattened)
- D-008: Breakeven SL = entry price exactly
- D-009: Stale position detection via reconciliation

**Phase 1 — Design**:
- `data-model.md`: 5 entities with full field definitions, state transitions, invariants, validation rules
- `contracts/execution_engine.md`: Full function signatures for all 6 modules + error handling contract + config schema
- `quickstart.md`: Usage guide, pipeline diagram, new file layout, test commands, kill-switch CLI operations

**plan.md**: Architecture diagram, 7-phase delivery plan, constitution check (all gates PASS), module breakdown, test strategy, 3 risk items.

**Agent context**: Updated `CLAUDE.md` via `update-agent-context.ps1 -AgentType claude`.

## Outcome

- ✅ Impact: Complete spec005 implementation blueprint ready for `/sp.tasks`
- 🧪 Tests: 6 unit test files + 1 integration test file planned; coverage target ≥ 80%
- 📁 Files: 5 new files created in `specs/005-execution-engine/`; `plan.md` filled from template
- 🔁 Next prompts: `/sp.tasks` to generate `tasks.md` → `/sp.implement` to build `src/execution/`
- 🧠 Reflection: Key insight — `logs/trades.json` thread-safety overlap between `OrderManager._log_lock` (spec001) and new `audit_logger.py` (spec005) flagged as a risk; both write to same file; needs shared lock or refactor to single writer

## Evaluation notes (flywheel)

- Failure modes observed: None — all 9 design decisions resolved without ambiguity
- Graders run and results (PASS/FAIL): Constitution check PASS (all 9 CLAUDE.md guarantees verified)
- Prompt variant (if applicable): N/A — standard /sp.plan invocation
- Next experiment (smallest change to try): Consider whether `audit_logger.py` should absorb `OrderManager._log_trade()` responsibility to eliminate dual-lock risk on `logs/trades.json`
