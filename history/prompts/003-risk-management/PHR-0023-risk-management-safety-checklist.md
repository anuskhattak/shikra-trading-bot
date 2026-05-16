---
id: PHR-0023
title: risk-management-safety-checklist
stage: spec
date: 2026-05-16
surface: claude-code
model: claude-sonnet-4-6
feature: 003-risk-management
branch: 003-risk-management
user: anaskhattak
command: /sp.checklist specs/003-risk-management/spec.md
labels: [checklist, risk-safety, edge-cases, spec-quality]
links:
  spec: specs/003-risk-management/spec.md
  ticket: ""
  adr: ""
  pr: ""
files:
  - specs/003-risk-management/checklists/risk-safety.md
tests:
  - ""
---

## Prompt

spec003 spec.md ko sp.checklist karo — generate checklist only for specs/003-risk-management

## Response snapshot

Generated a new requirements quality checklist `specs/003-risk-management/checklists/risk-safety.md` (34 items, CHK001–CHK034) focused on edge cases, state transitions, and safety-critical requirement gaps not covered by the existing `requirements.md` (spec quality) and `implementation-review.md` (implementation tracking) checklists.

Key gaps surfaced:
- CHK002: zero `sl_atr_multiplier` → division-by-zero risk unspecified
- CHK006: `recovery_profit_pips` ownership undefined in spec
- CHK011: "session" term undefined (no UTC time ranges given)
- CHK024: hard cap vs minimum lot conflict unresolved
- CHK016: guard evaluation order not specified in `is_trading_allowed()`

## Outcome

- ✅ Impact: 34 new requirement quality items surfaced across 7 categories; spec gaps identified before implementation begins
- 🧪 Tests: N/A — checklist is a requirements artifact, not code
- 📁 Files: specs/003-risk-management/checklists/risk-safety.md (created)
- 🔁 Next prompts: Address the [Gap] items in spec.md, then proceed with sp.implement
- 🧠 Reflection: Two checklists already existed (requirements.md all-pass, implementation-review.md all-pending); new checklist correctly targets uncovered safety-critical and edge-case requirement quality

## Evaluation notes (flywheel)

- Failure modes observed: prerequisites script returned spec002 FEATURE_DIR instead of spec003 — user corrected mid-session
- Graders run and results (PASS/FAIL): N/A
- Prompt variant (if applicable): N/A
- Next experiment: Ask user which [Gap] items to resolve in spec before implementation
