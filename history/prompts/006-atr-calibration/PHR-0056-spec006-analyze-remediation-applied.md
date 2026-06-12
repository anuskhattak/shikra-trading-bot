---
id: PHR-0056
title: spec006-analyze-remediation-applied
stage: misc
date: 2026-05-22
surface: claude-code
model: claude-sonnet-4-6
feature: 006-atr-calibration
branch: 006-atr-calibration
user: anaskhattak
command: fix (remediation after /sp.analyze)
labels: [remediation, analyze, atr, spec006]
links:
  spec: specs/006-atr-calibration/spec.md
  ticket: ""
  adr: ""
  pr: ""
files:
  - specs/006-atr-calibration/spec.md
  - specs/006-atr-calibration/tasks.md
tests:
  - n/a
---

## Prompt

"inhain fix karo" — apply all 7 remediation edits identified in PHR-0055 /sp.analyze report

## Response snapshot

Applied all 7 fixes across spec.md and tasks.md:

**spec.md changes (5 edits):**
- C1: FR-010 reworded — clarifies orchestrator supplies bars, ATRService does not fetch data directly
- I2: FR-013 clarified — regime thresholds excluded from this module's config scope (they live in spec004)
- A1: ATRReading Key Entity updated — added bar_count field
- U1: New Assumption added — M5/H4 ATR available via generic get_atr(), consumed by spec007/spec008 later
- G1: New Assumption added — weekend/holiday OHLCV gaps handled implicitly via D-007 None fallback

**tasks.md changes (3 edits):**
- I1: Removed [P] markers from T005–T009 (all in same models.py file, sequential write)
- G2: Added SC-003 timing note to T025 — manual verification during spec008 integration test
- Note updated to reflect [P] marker removal rationale

## Outcome

- ✅ Impact: All 7 analysis findings resolved; spec and tasks now fully consistent
- 🧪 Tests: n/a
- 📁 Files: specs/006-atr-calibration/spec.md, specs/006-atr-calibration/tasks.md
- 🔁 Next prompts: /sp.implement
- 🧠 Reflection: C1 was the most critical fix — without it, implementer could have put MT5 fetch inside ATRService, breaking the pure/testable design and violating the no-broker-imports principle established across all src/ modules.

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): All 7 findings addressed
- Prompt variant (if applicable): n/a
- Next experiment: n/a
