---
id: PHR-0048
title: Phase 7 Partial Close US3 Tests
stage: green
date: 2026-05-21
surface: agent
model: claude-sonnet-4-6
feature: 005-execution-engine
branch: 005-execution-engine
user: anaskhattak
command: sp.phr (auto)
labels: [partial-close, reconcile-positions, manage-positions, us3, t019, t020, t021, t022, phase7, position-manager]
links:
  spec: specs/005-execution-engine/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - tests/unit/test_execution_position_manager.py
  - specs/005-execution-engine/tasks.md
tests:
  - tests/unit/test_execution_position_manager.py (31 tests — all pass)
  - tests/unit/ full suite (327 tests — all pass, zero regressions)
---

## Prompt

phase 7 implement karo

## Response snapshot

Phase 7 (T019–T022 — US3 Partial Close) implement kiya gaya. T019–T021 (apply_partial_close, reconcile_positions, manage_positions) pehle se position_manager.py mein implement the — sirf T022 tests missing the. 12 naye tests likhe: TestApplyPartialClose (6), TestReconcilePositions (3), TestManagePositions (3). 327/327 pass, zero regressions. tasks.md mein T019–T022 complete [x] mark kiye.

## Outcome

- ✅ Impact: T019–T022 (Phase 7 — US3) complete. apply_partial_close() lot ratio + rounding + breakeven SL verified; reconcile_positions() externally-closed detection verified; manage_positions() TP2 priority + no-trailing-same-bar invariant (D-006) verified.
- 🧪 Tests: 327/327 pass — 12 new position_manager T022 tests, 315 pre-existing (zero regressions)
- 📁 Files: 1 test file (12 new tests added to test_execution_position_manager.py), tasks.md (T019–T022 checkmarks)
- 🔁 Next prompts: Phase 8 (T023–T028) — manage_open_positions(), open_positions property, config.yaml block, __init__.py exports, integration test, coverage gate
- 🧠 Reflection: T019–T021 implementations were already in position_manager.py from Phase 6 session (same file, written ahead). Discovery: always read the implementation file before writing tests — saves duplicate work. The `activation_distance=100` trick in test_tp1_hit_triggers_partial_close isolates TP1 behavior without trailing firing on the same bar.

## Evaluation notes (flywheel)

- Failure modes observed: None — implementation already existed; 12 tests passed on first run. Pre-checking the implementation file before writing tests was key.
- Graders run and results (PASS/FAIL): pytest 327/327 PASS
- Prompt variant (if applicable): null
- Next experiment (smallest change to try): In Phase 8, manage_open_positions() test should verify kill-switch allows position management while blocking new execute_signal() calls — use two separate mock scenarios to confirm US4 S2 acceptance scenario.
