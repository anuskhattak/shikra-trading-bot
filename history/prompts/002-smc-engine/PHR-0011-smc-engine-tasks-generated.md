---
id: PHR-0011
title: smc-engine-tasks-generated
stage: tasks
date: 2026-05-14
surface: claude-code-cli
model: claude-sonnet-4-6
feature: 002-smc-engine
branch: 002-smc-engine
user: anaskhattak
command: /sp.tasks
labels: [tasks, smc-engine, signal-detection, bos-choch, fvg, order-block, liquidity-sweep, scorer]
links:
  spec: specs/002-smc-engine/spec.md
  ticket: ""
  adr: ""
  pr: ""
files:
  - specs/002-smc-engine/tasks.md (created)
tests:
  - "All 25 tasks include TDD test tasks for SC-008 (≥80% coverage requirement)"
---

## Prompt

spec002 ke task banao

## Response snapshot

Generated `specs/002-smc-engine/tasks.md` with 25 tasks across 8 phases:

- **Phase 1 (Setup)**: T001–T004 — directory structure, dependencies, logs/, config.yaml smc_engine section
- **Phase 2 (Foundational)**: T005–T007 — `src/engine/models.py` with all 6 enums + 5 dataclasses; `__init__.py` stub
- **Phase 3 (US1 P1)**: T008–T011 — BOS/CHoCH: failing tests first, then `swing.py` + `bos_choch.py`
- **Phase 4 (US2 P2)**: T012–T013 — FVG: failing tests + `fvg.py`
- **Phase 5 (US3 P3)**: T014–T015 — Order Block: failing tests + `order_block.py`
- **Phase 6 (US4 P4)**: T016–T017 — Liquidity Sweep: failing tests + `liquidity_sweep.py`
- **Phase 7 (US5 P1)**: T018–T022 — Scorer + Orchestrator: failing tests + `scorer.py` + `smc_engine.py` + `__init__.py` final exports
- **Phase 8 (Polish)**: T023–T025 — coverage ≥80% validation, <100ms benchmark, quickstart smoke test

Key structural decisions:
- US1 and US5 are both P1 but ordered correctly: US1 first (US5 consumes its output)
- Phases 3–6 can run in parallel after Phase 2 (four independent detectors)
- TDD enforced for all 5 detection modules per SC-008
- entry_zone priority: OB body primary, FVG fallback (D-004)
- false_signals.json logging wired into scorer (FR-023)

## Outcome

- ✅ Impact: 25 immediately executable tasks covering all 5 user stories + polish phase
- 🧪 Tests: 7 test files planned (test_engine_swing, bos_choch, fvg, order_block, liquidity_sweep, scorer, smc_engine); TDD-first throughout
- 📁 Files: specs/002-smc-engine/tasks.md created
- 🔁 Next prompts: `/sp.implement` to execute tasks T001–T025; or `sp.analyze` for cross-artifact consistency check
- 🧠 Reflection: US5 (scorer/orchestrator) naturally falls last despite P1 priority — it integrates all detectors. Parallelism opportunity in Phases 3–6 is the key throughput win.

## Evaluation notes (flywheel)

- Failure modes observed: Prerequisites script returned 001 as FEATURE_DIR (hardcoded); manually overrode to 002-smc-engine directory
- Graders run and results (PASS/FAIL): Format validation — all 25 tasks follow `- [ ] [TID] [P?] [Story?] description with file path` pattern ✅
- Prompt variant (if applicable): none
- Next experiment: Test if parallel streams A/B/C/D (Phases 3–6) can each be handed to separate sp.implement agents simultaneously
