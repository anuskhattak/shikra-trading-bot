---
id: PHR-0022
title: Spec003 Risk Management Clarifications
stage: spec
date: 2026-05-16
surface: agent
model: claude-sonnet-4-6
feature: 003-risk-management
branch: 001-mt5-broker
user: anaskhattak
command: /sp.clarify
labels: ["spec003", "risk-management", "clarifications", "utc", "edge-cases", "naming"]
links:
  spec: specs/003-risk-management/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - specs/003-risk-management/spec.md
  - specs/003-risk-management/data-model.md
tests:
  - none
---

## Prompt

/sp.clarify

## Response snapshot

5 ambiguities detect hui aur resolve ki gayin spec003 (Risk Management) mein:
1. Timezone → UTC throughout (FR-019, FR-021, US3 scenario 3)
2. ATR=0 edge case → ValueError raise karo (FR-006a new)
3. Mid-day cold start → current equity, documented limitation (FR-015a new)
4. `sl_distance_pips` naming → renamed to `sl_distance` in price units (FR-007, data-model.md)
5. Log write failure → silent fail, trade proceeds (NFR-005 updated)

## Outcome

- ✅ Impact: 5/5 clarifications resolved — spec003 ready for `/sp.plan` or implementation
- 📁 Files: `specs/003-risk-management/spec.md` (Clarifications section + FR-006a + FR-015a + FR-007 + NFR-005 updated), `specs/003-risk-management/data-model.md` (`sl_distance_pips` → `sl_distance`)
- 🔁 Next: `003-risk-management ka phase1 implement karo` ya `/sp.plan` run karo

## Evaluation notes (flywheel)

- Failure modes observed: Script ne spec002 resolve kiya (branch mismatch) — manually spec003 load kiya.
- Next experiment: `check-prerequisites.ps1` mein active feature override parameter add karna useful hoga.
