---
id: PHR-0012
title: smc-engine-tasks-analysis
stage: tasks
date: 2026-05-14
surface: claude-code-cli
model: claude-sonnet-4-6
feature: 002-smc-engine
branch: 002-smc-engine
user: anaskhattak
command: /sp.analyze
labels: [analyze, tasks, smc-engine, consistency-check, coverage-gap]
links:
  spec: specs/002-smc-engine/spec.md
  ticket: ""
  adr: ""
  pr: ""
files:
  - specs/002-smc-engine/spec.md (read)
  - specs/002-smc-engine/plan.md (read)
  - specs/002-smc-engine/tasks.md (read)
  - specs/002-smc-engine/data-model.md (read)
  - specs/002-smc-engine/contracts/smc_engine.md (read)
tests:
  - "No tests modified — read-only analysis"
---

## Prompt

spec002 ki task.md file plan ke mtabik hai?

## Response snapshot

Cross-artifact consistency analysis of spec.md + plan.md + tasks.md for 002-smc-engine.

**Result**: No CRITICAL issues. 1 HIGH, 5 MEDIUM, 2 LOW.

Key findings:
- C1 (HIGH): NFR-001 (inline SMC comments) not covered by any task — gap in auditability requirement
- C2 (MEDIUM): SC-003 (hand-labelled OB 95% validation dataset) has no task and is not marked out-of-scope
- C3 (MEDIUM): SC-007 (false_signals.json ≤1s) has no timing test
- F1 (MEDIUM): T004 assumes config.yaml exists — no task creates it
- F2 (MEDIUM): T007 stub __init__.py behaviour unspecified — could cause import errors between T007 and T022
- F3 (MEDIUM): test_engine_smc_engine.py classified as "unit" but is multi-module integration test
- U1 (MEDIUM): No conftest.py fixture factory task — 7 test files will independently build synthetic DataFrames
- U2 (LOW): false_signals.json initialization unspecified (scorer vs. pre-created)
- A1 (LOW): pip_tolerance documented in "pips" in spec but "float dollars" in contract — inconsistent units labelling
- D1 (LOW): candle-close rule stated 3 times — intentional for auditability, no action needed

Coverage: 90% (33/36 requirements covered, excl. SC-009 backtest which is out of scope).
All 25 tasks map to at least one requirement — no orphan tasks.

## Outcome

- ✅ Impact: Tasks.md is 90% aligned with plan/spec. Implementation can proceed with minor fixes.
- 🧪 Tests: Read-only analysis — no tests modified
- 📁 Files: No files modified (read-only command)
- 🔁 Next prompts: Apply remediation edits to tasks.md, then `/sp.implement`
- 🧠 Reflection: NFR-001 inline comments gap is the most important fix — it's a CLAUDE.md mandate and directly impacts signal auditability, which is a core trading system guarantee.

## Evaluation notes (flywheel)

- Failure modes observed: Prerequisites script returned 001 as FEATURE_DIR; constitution.md absent; CLAUDE.md used as authority fallback
- Graders run and results: Coverage table verified against all FR/NFR/SC line items ✅
- Prompt variant: none
- Next experiment: Check if conftest.py fixture gap causes test drift after implementing 2+ phases independently
