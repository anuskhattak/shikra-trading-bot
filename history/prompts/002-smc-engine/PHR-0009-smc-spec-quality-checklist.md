---
id: PHR-0009
title: SMC Spec Quality Checklist
stage: spec
date: 2026-05-12
surface: claude-code
model: claude-sonnet-4-6
feature: 002-smc-engine
branch: 001-mt5-broker
user: wshahrukh0@gmail.com
command: /sp.checklist spec quality check karo
labels: [checklist, spec-quality, smc-engine, requirements-review]
links:
  spec: specs/002-smc-engine/spec.md
  ticket: ~
  adr: ~
  pr: ~
files:
  - specs/002-smc-engine/checklists/spec-quality.md
tests: ~
---

## Prompt

/sp.checklist spec quality check karo — full spec quality audit for 002-smc-engine before /sp.plan.

## Response snapshot

Generated `specs/002-smc-engine/checklists/spec-quality.md` with 38 checklist items across 8 categories testing requirements quality (not implementation):

- Requirement Completeness (7 items) — missing OB TESTED status FR, entry_zone fallback, input validation
- Requirement Clarity (7 items) — "established trend" undefined, ML_CONFIDENCE_THRESHOLD misnaming, confidence formula ambiguity
- Requirement Consistency (5 items) — stateless NFR-002 vs file-write FR-023 conflict, SC-009 scope conflict, OB TESTED status conflict
- Acceptance Criteria Quality (4 items) — hand-labelled dataset dependency, determinism measurability
- Scenario Coverage (4 items) — htf_bias=NEUTRAL case, Liquidity Sweep without CHoCH
- Edge Case Coverage (5 items) — news spike measurability, overlapping FVGs, consecutive BOS
- Non-Functional Requirements (3 items) — worst-case performance, memory bounds, error handling
- Dependencies & Assumptions (3 items) — config.yaml schema, MT5 contract validation

Top 5 blocking issues identified before /sp.plan can proceed.

## Outcome

- ✅ Impact: 38 requirement quality checks generated; 5 blocking issues surfaced
- 🧪 Tests: N/A (checklist validates requirements, not code)
- 📁 Files: specs/002-smc-engine/checklists/spec-quality.md created
- 🔁 Next prompts: Address blocking issues in spec.md, then /sp.plan
- 🧠 Reflection: NFR-002 (stateless) vs FR-023 (file write) is a classic spec conflict — "stateless" should be scoped to signal computation, not logging side effects

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): ~
- Prompt variant (if applicable): ~
- Next experiment: ~
