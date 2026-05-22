---
id: PHR-0039
title: Execution Engine Tasks Generated
stage: tasks
date: 2026-05-20
surface: claude-code
model: claude-sonnet-4-6
feature: 005-execution-engine
branch: 005-execution-engine
user: anaskhattak
command: /sp.tasks
labels: [tasks, execution-engine, spec005, implementation]
links:
  spec: specs/005-execution-engine/spec.md
  plan: specs/005-execution-engine/plan.md
  tasks: specs/005-execution-engine/tasks.md
  pr: N/A
files:
  - specs/005-execution-engine/tasks.md
tests: []
---

## Prompt

/sp.tasks — Generate implementable tasks.md for spec005 (Execution Engine) from plan.md, spec.md, data-model.md, contracts/execution_engine.md, and research.md.

## Response snapshot

Loaded all 5 design documents from `specs/005-execution-engine/`. Extracted 5 user stories (US1–US5) from spec.md and mapped them to the 7-phase delivery order from plan.md. Generated 28 tasks across 8 phases:

**Phase 1 — Setup (1 task)**: Create `src/execution/` package directory skeleton.

**Phase 2 — Foundational / models.py (2 tasks)**: All 5 dataclasses + `AuditAction` enum (8 values); unit tests for invariants and completeness. Blocks all user story phases.

**Phase 3 — US4 Kill-Switch (2 tasks, parallelizable with Phase 4)**: `kill_switch.py` with atomic temp-file-rename write; unit tests covering file-absent safe default and malformed JSON safe default.

**Phase 4 — US5 Audit Trail (4 tasks, parallelizable with Phase 3)**: `audit_logger.py` with single module-level `AUDIT_LOG_LOCK`; unit tests including concurrent-write corruption check; **T008 (critical)** migrates `OrderManager._log_trade()` to use `audit_logger.write_audit_entry()` — eliminates dual-lock race on `logs/trades.json`.

**Phase 5 — US1 Order Placement (6 tasks) 🎯 MVP**: All 5 preflight checks + `run_preflight()` orchestrator; `ExecutionEngine.__init__()` + `execute_signal()`; unit tests for all rejection scenarios. MVP complete after this phase.

**Phase 6 — US2 Trailing Stop (3 tasks)**: `evaluate_trailing_stop()` pure function (LONG/SHORT unidirectional); `_apply_sl_modification()` with single retry; unit tests for non-regression and retry behaviour.

**Phase 7 — US3 Partial Close (4 tasks)**: `apply_partial_close()` (counter-direction `order_send` with `position=ticket_id`, lot rounding to 0.01, breakeven SL); `reconcile_positions()`; `manage_positions()` bar-level entry point; comprehensive unit tests including lot-mismatch and duplicate-close edge cases.

**Phase 8 — Integration (6 tasks)**: `manage_open_positions()` + `open_positions` property; `config.yaml` execution block; `__init__.py` public exports; integration test (full round-trip on MT5 demo); coverage gate (≥ 80%).

**Task totals**: 28 tasks — 6 marked [P] (parallelizable across different files), 21 carrying user story labels (US1–US5), 7 in setup/foundational/polish phases without story labels.

**MVP scope**: US4 + US5 + US1 (Phases 1–5, tasks T001–T015) — bot can place orders with audit trail and kill-switch armed.

## Outcome

- ✅ Impact: Complete, dependency-ordered task list for all 28 implementation tasks across 8 phases
- 🧪 Tests: N/A — task generation artifact; no code tests
- 📁 Files: `specs/005-execution-engine/tasks.md` created (28 tasks, 8 phases)
- 🔁 Next prompt: `/sp.red T002` — begin TDD red phase for `src/execution/models.py`
- 🧠 Reflection: T008 (dual-lock migration) is the highest-risk task — flagged prominently in tasks.md Notes section. Integration test T027 must run immediately after T008 to verify no JSON corruption before merging.

## Evaluation notes (flywheel)

- Failure modes observed: None — all 5 user stories cleanly mapped to distinct module boundaries
- Graders run: All 28 tasks pass checklist format (checkbox + ID + labels + file path)
- Key dependency insight: US2 (Trailing Stop) depends only on models.py — can be parallelized with US4/US5 by a second developer, saving ~1 day of elapsed time
- Next experiment: Consider whether T008 warrants its own ADR (migration of a live log writer mid-feature) — would document the retire-OrderManager-_log_trade decision with alternatives
