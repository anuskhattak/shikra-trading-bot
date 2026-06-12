---
id: PHR-0066
title: plan-007-h4-bias-engine
stage: plan
date: 2026-06-12
surface: claude-code
model: claude-sonnet-4-6
feature: 007-h4-bias-engine
branch: 007-h4-bias-engine
user: anaskhattak
command: /sp.plan
labels: [plan, h4-bias, smc, atR, swing-detection, scorer, pipeline]
links:
  spec: specs/007-h4-bias-engine/spec.md
  ticket: ~
  adr: ~
  pr: ~
files:
  - specs/007-h4-bias-engine/plan.md
  - specs/007-h4-bias-engine/research.md
  - specs/007-h4-bias-engine/data-model.md
  - specs/007-h4-bias-engine/quickstart.md
  - specs/007-h4-bias-engine/contracts/h4_bias_service.md
  - specs/007-h4-bias-engine/contracts/scorer_extension.md
tests:
  - tests/test_h4_bias.py (planned)
---

## Prompt

User invoked `/sp.plan` for feature 007-h4-bias-engine. Prior context: spec.md was completed in the same session (PHR-0065). User wants ML/DL model integration for accuracy; this spec is Phase 1 (ATR-based rule engine) designed to be replaced by LSTM in spec012.

## Response snapshot

Read 6 existing source files to understand codebase patterns: `analysis/models.py`, `analysis/atr_service.py`, `engine/swing.py`, `engine/models.py`, `engine/scorer.py`, `orchestrator/pipeline.py`.

Key findings:
- `detect_swing_points()` already exists and is reusable — no duplication needed
- `Bias` enum already in `src/engine/models.py` — add `RANGING` value
- `EntrySignal` missing `h4_bias` + `h4_bias_strength` fields — add with defaults
- `pipeline.py` hardcodes `Bias.NEUTRAL` — needs H4BiasService wired in
- `scorer.py` does HTF filter but no alignment boost — update needed

Generated 6 planning artifacts:
- `plan.md`: Full implementation plan, 7 phases (A–G), risk register, dependency map
- `research.md`: 8 research decisions (algorithm, enum location, RANGING block, alignment boost, EntrySignal fields, smc_engine audit, LSTM replaceability, backtest compat)
- `data-model.md`: H4BiasResult, Bias enum extension, EntrySignal updates, PipelineContext update, config schema
- `contracts/h4_bias_service.md`: H4BiasService, classify_bias(), LSTM replaceability contract
- `contracts/scorer_extension.md`: score_and_assemble() signature update, scoring logic changes
- `quickstart.md`: Integration guide, config, test commands

Architecture: 1 new file (`src/analysis/h4_bias.py`), 5 modified files, follows ATRService pattern exactly.

## Outcome

- ✅ Impact: Complete implementation blueprint — developer can implement directly from plan.md + contracts
- 🧪 Tests: 9 unit tests specified in plan.md Phase G
- 📁 Files: plan.md, research.md, data-model.md, quickstart.md, 2 contracts
- 🔁 Next prompts: `/sp.tasks` → `/sp.implement`
- 🧠 Reflection: Critical insight — smc_engine.py needs `htf_bias_strength` threaded through; backtest engine also needs H4BiasService injection. Both captured in risk register.

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): Constitution check — PASS (6/6 gates)
- Prompt variant (if applicable): ~
- Next experiment: ~
