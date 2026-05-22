---
id: PHR-0047
title: Phase 6 Trailing Stop Position Manager
stage: green
date: 2026-05-20
surface: agent
model: claude-sonnet-4-6
feature: 005-execution-engine
branch: 005-execution-engine
user: anaskhattak
command: sp.phr (auto)
labels: [trailing-stop, position-manager, sl-modification, unidirectional, retry, phase6, T016, T017, T018, US2]
links:
  spec: specs/005-execution-engine/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - src/execution/position_manager.py
  - tests/unit/test_execution_position_manager.py
  - specs/005-execution-engine/tasks.md
tests:
  - tests/unit/test_execution_position_manager.py (19 tests — all pass)
  - tests/unit/ full suite (315 tests — all pass, zero regressions)
---

## Prompt

phase6 implement karo

## Response snapshot

Phase 6 (T016–T018 — US2 Trailing Stop) implement kiya gaya. `evaluate_trailing_stop()` pure function mein LONG/SHORT symmetric logic, `dataclasses.replace()` se functional update (no mutation), aur `_apply_sl_modification()` mein MT5 TRADE_ACTION_SLTP request with exactly-one-retry pattern. 19 naye tests, 315/315 pass.

## Outcome

- ✅ Impact: T016–T018 (Phase 6 — US2) complete. Trailing stop logic tested aur working — LONG aur SHORT dono directions ke liye unidirectional invariant enforce hota hai. Retry pattern confirmed: 2 total order_send calls, SL_MODIFICATION_FAILED entry written on double failure.
- 🧪 Tests: 315/315 pass — 19 position_manager tests, 296 pre-existing (zero regressions)
- 📁 Files: 1 implementation file (position_manager.py skeleton → full Phase 6 code), 1 test file, tasks.md (T016–T018 checkmarks)
- 🔁 Next prompts: Phase 7 (T019–T022) — apply_partial_close(), reconcile_positions(), manage_positions() implement karo (US3)
- 🧠 Reflection: `dataclasses.replace()` functional update pattern ensures original PositionState is never mutated — important because multiple callers may hold references to the same state. `test_original_position_not_mutated` explicitly verifies this invariant.

## Evaluation notes (flywheel)

- Failure modes observed: None — all 19 tests passed on first run. The pure function design of evaluate_trailing_stop() made testing straightforward without any mocking complexity.
- Graders run and results (PASS/FAIL): pytest 315/315 PASS
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): In Phase 7, apply_partial_close() and manage_positions() tests will need careful fixture setup since they combine trailing + partial close logic in one bar. Use parametrize to cover TP2/TP1/trailing priority edge cases.
