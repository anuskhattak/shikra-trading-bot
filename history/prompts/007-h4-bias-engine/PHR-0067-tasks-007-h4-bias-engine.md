---
id: PHR-0067
title: tasks-007-h4-bias-engine
stage: tasks
date: 2026-06-12
surface: claude-code
model: claude-sonnet-4-6
feature: 007-h4-bias-engine
branch: 007-h4-bias-engine
user: anaskhattak
command: /sp.tasks
labels: [tasks, h4-bias, smc, scorer, pipeline, unit-tests]
links:
  spec: specs/007-h4-bias-engine/spec.md
  ticket: ~
  adr: ~
  pr: ~
files:
  - specs/007-h4-bias-engine/tasks.md
tests:
  - tests/test_h4_bias.py (planned, T014–T018, T028–T030, T032–T034)
---

## Prompt

User invoked `/sp.tasks` for feature 007-h4-bias-engine. All design artifacts (spec, plan, research, data-model, contracts) were available from the same session.

## Response snapshot

Generated `specs/007-h4-bias-engine/tasks.md` with 36 tasks across 6 phases:

- Phase 1 (T001–T002): Config schema update — add h4_bias and scoring weight keys to config.yaml
- Phase 2 (T003–T006): Foundational model changes — Bias.RANGING, EntrySignal h4_bias/h4_bias_strength fields, PipelineContext h4_bias_result field
- Phase 3 (T007–T018): US1+US2 (P1) — H4BiasService creation in src/analysis/h4_bias.py, RANGING block in scorer, 5 unit tests
- Phase 4 (T019–T030): US3+US4 (P2) — htf_bias_strength threading, alignment boost, MTF multiplier, pipeline Stage 0 wiring, backtest engine update, 3 unit tests
- Phase 5 (T031–T032): US5 (P3) — bias transition logging, EntrySignal audit test
- Phase 6 (T033–T036): Polish — counter-trend and neutral-bias tests, regression run, import check

11 parallelizable tasks identified (all test tasks). MVP = Phase 1–3 (18 tasks, US1+US2 complete).

## Outcome

- ✅ Impact: Immediately executable task list; each phase has an independent test checkpoint
- 🧪 Tests: 11 unit tests specified (T014–T018, T028–T030, T032–T034) in tests/test_h4_bias.py
- 📁 Files: specs/007-h4-bias-engine/tasks.md
- 🔁 Next prompts: `/sp.implement` to execute all tasks
- 🧠 Reflection: Phase 2 foundational tasks must be strictly sequential (all edit src/engine/models.py); if parallelized they would conflict. Marked correctly as non-parallel.

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): Format check — all 36 tasks have checkbox + ID + description + file path
- Prompt variant (if applicable): ~
- Next experiment: ~
