---
id: PHR-0034
title: spec004-analyze-remediation
stage: misc
date: 2026-05-19
surface: claude-code-cli
model: claude-sonnet-4-6
feature: 004-session-filters
branch: 004-session-filters
user: anaskhattak
command: /sp.analyze (remediation)
labels: [remediation, session-filters, consistency]
links:
  spec: specs/004-session-filters/spec.md
  ticket: ""
  adr: ""
  pr: ""
files:
  - specs/004-session-filters/spec.md
  - specs/004-session-filters/plan.md
  - specs/004-session-filters/data-model.md
  - specs/004-session-filters/quickstart.md
  - specs/004-session-filters/tasks.md
  - specs/004-session-filters/checklists/implementation-review.md
tests: []
---

## Prompt

User said "subko resolve karo" — fix all 11 findings from /sp.analyze (PHR-0033).

## Response snapshot

All 11 findings resolved across 6 files:

**I1 (HIGH) — Session UTC times vs local time**: spec.md FR-003 updated to local times (08:00–17:00 Europe/London, 08:00–17:00 America/New_York); Assumptions updated; plan/data-model/quickstart London close fixed "16:00"→"17:00"; filters_log added to logging section.

**I2 (MEDIUM) — SessionWindow missing**: Added `SessionWindow` dataclass to plan.md, data-model.md, tasks.md T004, and implementation-review.md CHK001b.

**I3 (MEDIUM) — VolatilityReading unused**: Changed `classify_regime()` return type from `VolatilityRegime` → `VolatilityReading` in plan.md, tasks.md T012, data-model.md note, and CHK020.

**I4 + C1 (MEDIUM) — Cooldown unimplemented**: Descoped to Spec 006. spec.md US4 Scenario 4 simplified (removed "cooldown period"); plan/data-model config yaml `cooldown_candles` removed; tasks.md T012 note added.

**I5 (MEDIUM) — signal_id missing from EntrySignal**: Added UUID generation note to tasks.md T014, data-model.md Key Entities table, and CHK026.

**I6 (MEDIUM) — metric_value type conflict**: spec.md US4 Scenario 3 updated to "metric_value = ATR ratio (float)"; tasks.md T011 test updated; CHK023/CHK024 updated.

**U1 (MEDIUM) — No SC-001 timing test**: Added T013c timing test task to tasks.md; CHK033 updated to reference T013c.

**U2 (LOW) — filters_log missing from config**: Added `filters_log: logs/filter_decisions.json` to logging section in plan.md, data-model.md, quickstart.md; T002 description updated; CHK041 updated.

**A1 (LOW) — Spread threshold test ambiguity**: tasks.md T007 test renamed `test_spread_at_exact_threshold_allowed` + added `test_spread_one_cent_over_blocked`.

**U3 (LOW) — MT5 server time note**: Added explicit caller note to T006 description.

**I1 subtlety**: Also fixed London local_close from "16:00" → "17:00" (plan/data-model/quickstart) — summer UTC equivalent 07:00–16:00 now matches spec's stated approximate values.

## Outcome

- ✅ Impact: All 11 analysis findings resolved; artifacts fully consistent; implementation can begin
- 🧪 Tests: T013c added for SC-001 timing; T011 updated for VolatilityReading and metric_value; T007 test names corrected
- 📁 Files: 6 files updated
- 🔁 Next prompts: `/sp.implement T001` or begin implementation
- 🧠 Reflection: London close time "16:00"→"17:00" was a plan generation error caught by the analysis — good catch

## Evaluation notes (flywheel)

- Failure modes observed: One Edit tool error (CHK020 exact match failed — needed to re-read file)
- Graders run and results (PASS/FAIL): N/A
- Prompt variant (if applicable): N/A
- Next experiment: N/A
