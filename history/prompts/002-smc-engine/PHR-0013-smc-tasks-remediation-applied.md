---
id: PHR-0013
title: smc-tasks-remediation-applied
stage: tasks
date: 2026-05-14
surface: claude-code-cli
model: claude-sonnet-4-6
feature: 002-smc-engine
branch: 002-smc-engine
user: anaskhattak
command: /sp.analyze (remediation)
labels: [tasks, remediation, nfr-001, inline-comments, config-yaml, conftest, integration-test]
links:
  spec: specs/002-smc-engine/spec.md
  ticket: ""
  adr: ""
  pr: ""
files:
  - specs/002-smc-engine/tasks.md (modified — 5 fixes applied)
tests:
  - "No tests modified — tasks.md edits only"
---

## Prompt

haan, yeh 5 fixes apply kar do

## Response snapshot

Applied 5 remediation edits to `specs/002-smc-engine/tasks.md` based on PHR-0012 analysis:

- **F1 (T004)**: "Add section" → "Create or update config.yaml at repo root" — prevents failure when file doesn't exist
- **U1 (T001)**: Extended to include `tests/unit/conftest.py` with `make_ohlcv(n, seed=42)` fixture factory — shared by all 7 test files
- **F2 (T007)**: Stub `__init__.py` now explicitly raises `NotImplementedError` for `generate_signal`; callers directed to `src.engine.models` until T022
- **C1 (T010/T011/T013/T015/T017)**: All 5 implementation tasks now mandate inline comments explaining the SMC rule per NFR-001
- **F3 (T019/T024/Phase7 checkpoint)**: Pipeline test moved from `tests/unit/test_engine_smc_engine.py` → `tests/integration/test_engine_pipeline.py`; T024 and Phase 7 checkpoint updated accordingly

## Outcome

- ✅ Impact: tasks.md now covers NFR-001 (inline SMC comments), config.yaml creation safety, shared test fixtures, clear stub behavior, and correct test classification
- 🧪 Tests: No test files modified — task descriptions updated only
- 📁 Files: specs/002-smc-engine/tasks.md (modified)
- 🔁 Next prompts: `/sp.implement` — all gaps resolved, ready for implementation
- 🧠 Reflection: The NFR-001 fix is the most impactful — without explicit instruction in each task, inline comments are commonly skipped during implementation, breaking the auditability guarantee that is central to the Shikra trading system.

## Evaluation notes (flywheel)

- Failure modes observed: None — all 5 edits applied cleanly with unique string matching
- Graders run and results: Verified each changed line post-edit ✅
- Prompt variant: none
- Next experiment: Verify during /sp.implement that inline comment enforcement actually lands in generated code
