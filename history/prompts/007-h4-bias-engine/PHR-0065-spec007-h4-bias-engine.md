---
id: PHR-0065
title: spec-007-h4-bias-engine
stage: spec
date: 2026-06-12
surface: claude-code
model: claude-sonnet-4-6
feature: 007-h4-bias-engine
branch: 007-h4-bias-engine
user: anaskhattak
command: /sp.specify 007-h4-bias-engine
labels: [spec, h4-bias, smc, trading, atR-calibration, phase1]
links:
  spec: specs/007-h4-bias-engine/spec.md
  ticket: ~
  adr: ~
  pr: ~
files:
  - specs/007-h4-bias-engine/spec.md
  - specs/007-h4-bias-engine/checklists/requirements.md
tests:
  - ~
---

## Prompt

User invoked `/sp.specify 007-h4-bias-engine` after reading project documentation (CLAUDE.md and SHIKRA_DOCUMENTATION.md). Prior context established the planned spec sequence: 007 (h4-bias-engine) → 008 (bot-orchestrator) → 011 (ml-signal-filter) → 012 (lstm-h4-bias) → MT5 live deploy. User also clarified they want ML/DL models for accuracy improvement, skipping spec010 (monitoring dashboard).

## Response snapshot

Created branch `007-h4-bias-engine` and wrote full feature specification at `specs/007-h4-bias-engine/spec.md`.

Spec covers:
- 5 user stories (P1–P3): bias detection, ranging trade block, signal score boost (+2.0 alignment, 1.3x MTF), recalibration on H4 bar close, audit logging
- 14 functional requirements (FR-001–FR-014) including LSTM replaceability interface (FR-014, deferred to spec012)
- 3 key entities: H4BiasResult, SwingPoint, BiasStateLog
- 6 measurable success criteria (SC-001–SC-006): ≥80% classification accuracy, ≥5% win rate improvement from ranging filter, 100% EntrySignal field coverage
- Edge cases: cold start, equal highs/lows, MT5 data gaps, mid-session bias transitions
- Assumptions: swing lookback=20, min swing size=H1_ATR×1.5, ATR period=14, spec006 (ATR calibration) is prerequisite

Quality checklist: all 14 items pass. Spec ready for `/sp.plan`.

## Outcome

- ✅ Impact: H4 bias engine fully specified; establishes the directional gating module that every H1 signal entry depends on
- 🧪 Tests: Unit test stubs for cold-start, classification accuracy, and RANGING block defined in acceptance scenarios
- 📁 Files: specs/007-h4-bias-engine/spec.md, specs/007-h4-bias-engine/checklists/requirements.md
- 🔁 Next prompts: `/sp.plan 007-h4-bias-engine` → `/sp.tasks` → `/sp.implement`
- 🧠 Reflection: Explicitly designed FR-014 (LSTM-replaceable interface) so Phase 3 (spec012) does not require refactoring downstream modules

## Evaluation notes (flywheel)

- Failure modes observed: None — spec derived cleanly from existing SHIKRA_DOCUMENTATION.md
- Graders run and results (PASS/FAIL): Quality checklist — PASS (14/14)
- Prompt variant (if applicable): ~
- Next experiment (smallest change to try): Add concrete swing detection algorithm pseudocode to spec if planner requests more precision
