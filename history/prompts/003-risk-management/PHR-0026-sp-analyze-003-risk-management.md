---
id: PHR-0026
title: sp-analyze-003-risk-management
stage: misc
date: 2026-05-16
surface: claude-code-cli
model: claude-sonnet-4-6
feature: 003-risk-management
branch: 003-risk-management
user: anaskhattak
command: /sp.analyze specs/003-risk-management
labels: [analyze, consistency, spec, plan, tasks, risk-management]
links:
  spec: specs/003-risk-management/spec.md
  ticket: —
  adr: —
  pr: —
files:
  - specs/003-risk-management/spec.md
  - specs/003-risk-management/plan.md
  - specs/003-risk-management/tasks.md
tests:
  - none (read-only analysis)
---

## Prompt

Run /sp.analyze for specs/003-risk-management.

Use only these files as the source of truth:
- specs/003-risk-management/spec.md
- specs/003-risk-management/plan.md
- specs/003-risk-management/tasks.md

## Response snapshot

Performed full cross-artifact consistency analysis across spec.md (29 FRs + 5 NFRs), plan.md (7 modules, 7 design decisions, 7 phases), and tasks.md (19 tasks across 7 phases). Constitution validated against CLAUDE.md.

**Total findings: 16** across 6 detection categories.
- 0 CRITICAL
- 4 HIGH (F1, F2, D1, B1)
- 8 MEDIUM
- 3 LOW + 1 duplication

**Key HIGH findings:**
- F1: Function name drift — spec FR-016 says `is_trading_allowed()` but plan/tasks implement `is_trade_limit_allowed()` with a different signature (adds `session` param). Causes test failures if not resolved before Phase 4 implementation.
- F2: Return type conflict — spec FR-012/FR-016 say functions return `(bool, str)` tuple; plan uses `TradeAllowedResult` dataclass.
- D1: Constitution gap — CLAUDE.md §3 requires all decisions to produce trace logs; NFR-005 only logs blocking events. Successful `evaluate_trade_risk()` calls produce no audit trail.
- B1: `sl_pips` param name in FR-001 contradicts the clarification that renamed it to `sl_distance` (price units); also `calculate_sl_pips()` in plan still uses old naming.

**Coverage**: 85% overall (29/34 requirements have ≥1 task). FR-015a (startup init), FR-016 (name drift), NFR-003 (mutability contract), NFR-004 (no verification task) have partial/no coverage.

## Outcome

- ✅ Impact: 16 actionable findings produced; 4 HIGH issues identified that must be resolved before /sp.implement to avoid test failures and constitution violations.
- 🧪 Tests: No tests run (read-only analysis)
- 📁 Files: No files modified
- 🔁 Next prompts: /sp.specify (patch FR-001, FR-012, FR-016, add NFR-006); /sp.plan (rename calculate_sl_pips, align return types); /sp.tasks (add startup test, logging task, mypy task)
- 🧠 Reflection: The most structurally significant finding is F1 (function name drift) — it touches spec, plan, tasks, and all three test files. The constitution gap D1 is important because the risk module is the primary decision point but logs only half the decisions. Resolving B1 (sl_pips → sl_distance) prevents a subtle unit mismatch that would be hard to debug at runtime.

## Evaluation notes (flywheel)

- Failure modes observed: check-prerequisites.ps1 didn't accept -FeatureDir param; fell back to direct file reads — no impact on analysis quality.
- Graders run and results (PASS/FAIL): N/A (analysis task)
- Prompt variant (if applicable): —
- Next experiment (smallest change to try): Test whether passing --feature flag to check-prerequisites resolves FEATURE_DIR detection for non-active features.
