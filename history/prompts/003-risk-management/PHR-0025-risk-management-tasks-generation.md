---
id: PHR-0025
title: risk-management-tasks-generation
stage: tasks
date: 2026-05-16
surface: claude-code
model: claude-sonnet-4-6
feature: 003-risk-management
branch: 002-smc-engine
user: anaskhattak
command: /sp.tasks specs/003-risk-management
labels: [tasks, risk-management, task-generation, story-labels]
links:
  spec: specs/003-risk-management/spec.md
  ticket: ""
  adr: ""
  pr: ""
files:
  - specs/003-risk-management/tasks.md
tests:
  - ""
---

## Prompt

generate task for spec003

## Response snapshot

`tasks.md` already existed (18 tasks, T001–T018) from a previous session. Reviewed and updated it to conform to the strict sp.tasks format:

**Changes made to tasks.md**:
1. Added [US?] story labels to all user story phase tasks:
   - Phase 2 tasks → [US1] (lot sizing) and [US2] (SL/TP) labels
   - Phase 3 tasks → [US3] (drawdown guard)
   - Phase 4 tasks → [US4] (trade limits)
   - Phase 5 tasks → [US5] (recovery mode)
2. Split T005 (combined lot+SL/TP tests) into T005 [US1] and T005b [US2] for traceability
3. Added Dependencies block showing phase execution order (visual ASCII graph)
4. Added "Goal" and "Independent Test" criteria to each user story phase header
5. Added Implementation Strategy section (MVP vs full delivery vs priority order)
6. Task count increased from 18 → 19 (due to T005b split)

**Phase summary**:
- Phase 1: Setup & Models — T001–T004 (4 tasks, blocking)
- Phase 2: US1+US2 — T005, T005b, T006 (3 tasks, lot_calculator.py)
- Phase 3: US3 — T007–T008 (2 tasks, drawdown_guard.py)
- Phase 4: US4 — T009–T010 (2 tasks, trade_limits.py)
- Phase 5: US5 — T011–T012 (2 tasks, recovery_mode.py)
- Phase 6: Orchestrator — T013–T014 (2 tasks, risk_manager.py + integration tests)
- Phase 7: Polish — T015–T018 (4 tasks, coverage + cleanup)

## Outcome

- ✅ Impact: tasks.md updated with full sp.tasks-compliant format; 19 tasks across 7 phases, all story-labeled
- 🧪 Tests: N/A — task artifact, no code changed
- 📁 Files: specs/003-risk-management/tasks.md (updated)
- 🔁 Next prompts: sp.implement for spec003 — start with Phase 1 (T001–T004)
- 🧠 Reflection: setup-plan.ps1 / check-prerequisites.ps1 continue to auto-detect current git branch (002-smc-engine) and return spec002 paths — workaround is to use direct paths for spec003 artifacts

## Evaluation notes (flywheel)

- Failure modes observed: check-prerequisites.ps1 returns spec002 FEATURE_DIR due to current branch being 002-smc-engine; create-phr.sh not found (no bash scripts in .specify/scripts/bash/)
- Graders run and results (PASS/FAIL): N/A — planning artifact
- Prompt variant (if applicable): N/A
- Next experiment: Consider adding -FeatureDir override flag to powershell scripts to bypass branch-detection for multi-feature workflows
