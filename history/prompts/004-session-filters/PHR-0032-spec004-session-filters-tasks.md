---
id: PHR-0032
title: spec004-session-filters-tasks
stage: tasks
date: 2026-05-19
surface: claude-code-cli
model: claude-sonnet-4-6
feature: 004-session-filters
branch: 004-session-filters
user: anaskhattak
command: /sp.tasks
labels: [tasks, session-filters, filters, unit-tests, tdd]
links:
  spec: specs/004-session-filters/spec.md
  ticket: ""
  adr: ""
  pr: ""
files:
  - specs/004-session-filters/tasks.md
tests:
  - tests/unit/test_filters_session.py
  - tests/unit/test_filters_spread.py
  - tests/unit/test_filters_news.py
  - tests/unit/test_filters_volatility.py
  - tests/unit/test_filters_trade_gate.py
  - tests/integration/test_filters_pipeline.py
---

## Prompt

User invoked `/sp.tasks` for Spec 004 — Session & Pre-Trade Filters.

Context: plan.md, research.md, data-model.md, quickstart.md all generated in prior /sp.plan session. Spec has 4 user stories (US1: Session P1, US2: Spread P1, US3: News P2, US4: Volatility P2). SC-007 requires ≥80% test coverage.

## Response snapshot

Generated `specs/004-session-filters/tasks.md` with 20 tasks across 7 phases.

**Structure:**
- Phase 1 (T001–T004): Setup & Models — models.py, config.yaml updates, news_calendar.json stub
- Phase 2 (T005–T006): US1 Session Filter — 11 unit tests (DST scenarios, holidays, boundaries) + implementation
- Phase 3 (T007–T008): US2 Spread Filter — 7 unit tests + implementation
- Phase 4 (T009–T010): US3 News Filter — 9 unit tests (fail-safe scenarios) + implementation
- Phase 5 (T011–T012): US4 Volatility Filter — 9 unit tests (regime boundaries) + implementation
- Phase 6 (T013, T013b, T014): Orchestrator trade_gate.py — unit + integration tests + implementation
- Phase 7 (T015–T019): Polish, coverage, no-MT5 check, implementation-review.md

**Key notes in tasks:**
- `datetime.now(timezone.utc)` not `datetime.utcnow()` (UTC-aware requirement)
- `tzdata` package required on Windows for `zoneinfo`
- Session boundary: inclusive start, exclusive end `[open, close)`
- Phases 2–5 fully parallel after Phase 1
- Tests must FAIL before implementation (TDD)

## Outcome

- ✅ Impact: 20 immediately executable tasks; any task is completable without additional context
- 🧪 Tests: 36 specific test cases named across 6 test files; all mapped to spec FRs and acceptance scenarios
- 📁 Files: specs/004-session-filters/tasks.md
- 🔁 Next prompts: `/sp.implement` or begin T001 manually
- 🧠 Reflection: Phases 2–5 are fully parallel — single-developer should do P1 first (session+spread), then P2 (news+volatility); avoids news/volatility filter adding complexity before basics are confirmed

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): N/A
- Prompt variant (if applicable): N/A
- Next experiment: At T006 implementation, verify `tzdata` is in requirements.txt for Windows compatibility
