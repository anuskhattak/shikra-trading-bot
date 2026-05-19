---
id: PHR-0033
title: spec004-analyze-consistency-review
stage: misc
date: 2026-05-19
surface: claude-code-cli
model: claude-sonnet-4-6
feature: 004-session-filters
branch: 004-session-filters
user: anaskhattak
command: /sp.analyze
labels: [analyze, consistency, session-filters, review]
links:
  spec: specs/004-session-filters/spec.md
  ticket: ""
  adr: ""
  pr: ""
files: []
tests: []
---

## Prompt

User invoked `/sp.analyze` for Spec 004 — Session & Pre-Trade Filters.

Context: spec.md, plan.md, tasks.md, data-model.md all complete. Pre-implementation consistency check.

## Response snapshot

Read-only analysis of spec.md × plan.md × tasks.md. 11 findings across 5 categories.

**Severity breakdown:**
- CRITICAL: 0
- HIGH: 1 (I1 — session UTC times vs local time implementation)
- MEDIUM: 5 (I2 SessionWindow missing, I3 VolatilityReading unused, I4 cooldown unimplemented, I5 signal_id missing from EntrySignal, I6 metric_value type conflict)
- LOW: 4 (U2 log path config, A1 spread test ambiguity, U3 MT5 server time, C1 cooldown gap)

**Key finding (I1 HIGH):** Spec FR-003 says London = 07:00–16:00 UTC, NY = 12:00–21:00 UTC. Plan implements LOCAL time (08:00 local + zoneinfo). These only match in summer DST. In winter: London opens 08:00 UTC (spec says 07:00), NY opens 13:00 UTC (spec says 12:00). Plan implementation is correct; spec text needs updating.

**Key finding (I5 MEDIUM):** `evaluate_filters(signal_id: str)` requires signal_id parameter but `EntrySignal` (src/engine/models.py) has no signal_id field. No task covers UUID generation for this.

**Key finding (I4 MEDIUM):** US4 Scenario 4 (cooldown after EXTREME regime) has config entry (`cooldown_candles: 3`) but zero implementation tasks or tests. Acceptance scenario will fail.

All 15 FRs have at least 1 task. SC-001 (<100ms) has no explicit timing test.
No constitution (CLAUDE.md) violations found.

## Outcome

- ✅ Impact: Pre-implementation consistency verified; 11 issues documented before any code written
- 🧪 Tests: N/A (read-only analysis)
- 📁 Files: No files modified (read-only)
- 🔁 Next prompts: Remediate I1 in spec.md, I5 in tasks.md, decide I4 (implement or descope); then `/sp.implement`
- 🧠 Reflection: I1 (session time inconsistency) is the most impactful — it would cause DST test failures silently if uncaught. Good catch pre-implementation.

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): N/A
- Prompt variant (if applicable): N/A
- Next experiment: N/A
