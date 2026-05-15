---
id: PHR-0008
title: SMC Spec Clarify — Q4 & Q5
stage: spec
date: 2026-05-12
surface: claude-code
model: claude-sonnet-4-6
feature: 002-smc-engine
branch: 001-mt5-broker
user: wshahrukh0@gmail.com
command: /sp.clarify
labels: [clarification, smc-engine, fvg, order-block, entry-zone]
links:
  spec: specs/002-smc-engine/spec.md
  ticket: ~
  adr: ~
  pr: ~
files:
  - specs/002-smc-engine/spec.md
tests: ~
---

## Prompt

Continuation of /sp.clarify for 002-smc-engine spec. 3 questions were already answered in a prior session. User asked to resume from Q4.

Q4: FVG fill and OB invalidation — does wick touch or candle close trigger status change?
Q5: When BOS + FVG + OB all align, which zone becomes EntrySignal.entry_zone?

## Response snapshot

**Q4 answered:** B — Candle-close rule. FVG is FILLED only when a candle closes inside the zone; OB is INVALIDATED only when a candle closes beyond the OB body. Wick entries do not count. Consistent with FR-004 (BOS/CHoCH candle-close rule). FR-007 and FR-011 updated.

**Q5 answered:** A — OB zone (top/bottom of OB body) is primary entry_zone. When no OB is present, entry_zone falls back to FVG boundaries. FR-017 updated. Edge Cases section updated with OB-absent fallback scenario.

Total session: 5/5 questions answered. All critical ambiguities resolved.

## Outcome

- ✅ Impact: FR-007, FR-011, FR-017 clarified — deterministic fill/invalidation rules and entry zone selection now unambiguous
- 🧪 Tests: Unit tests for FVG fill (wick vs close), OB invalidation (wick vs close), entry_zone source (OB primary, FVG fallback) now testable
- 📁 Files: specs/002-smc-engine/spec.md — Clarifications section updated, FR-007/011/017 updated, Edge Cases updated
- 🔁 Next prompts: /sp.plan — spec is now fully clarified, ready for implementation planning
- 🧠 Reflection: Candle-close rule consistency across all detection functions (BOS, FVG fill, OB invalidation) is a key design invariant — prevents wick-based false triggers

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): ~
- Prompt variant (if applicable): ~
- Next experiment: ~
