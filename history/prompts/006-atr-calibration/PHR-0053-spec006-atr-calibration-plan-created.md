---
id: PHR-0053
title: spec006-atr-calibration-plan-created
stage: plan
date: 2026-05-22
surface: claude-code
model: claude-sonnet-4-6
feature: 006-atr-calibration
branch: 006-atr-calibration
user: anaskhattak
command: /sp.plan
labels: [plan, atr, calibration, analysis, cache, volatility]
links:
  spec: specs/006-atr-calibration/spec.md
  ticket: ""
  adr: ""
  pr: ""
files:
  - specs/006-atr-calibration/plan.md
  - specs/006-atr-calibration/research.md
  - specs/006-atr-calibration/data-model.md
  - specs/006-atr-calibration/quickstart.md
  - specs/006-atr-calibration/contracts/atr_service.md
tests:
  - n/a (plan stage)
---

## Prompt

/sp.plan (on branch 006-atr-calibration, spec006 ATR Calibration Module)

## Response snapshot

Created full implementation plan for spec006 ATR Calibration Module. Artifacts produced:

**research.md**: 10 design decisions resolved — D-001 (simple avg ATR), D-002 (20-period reference), D-003 (bar-close cache), D-004 (stateful service class), D-005 (no MT5 in analysis module), D-006 (Timeframe enum = MT5 constants), D-007 (None not 0.0 on insufficient data), D-008 (invalid bar filtering), D-009 (integration points), D-010 (config namespace).

**data-model.md**: 6 entities defined — Timeframe, OHLCVBar, VolatilityRegime, AdaptiveMultipliers, ATRReading, ATRCache — with validation rules and state transitions.

**contracts/atr_service.md**: Full function signatures for 5 modules (models, atr_calculator, reference_atr, adaptive_multipliers, atr_service) with error contract table.

**quickstart.md**: Usage examples for all integration points (volatility_filter, lot_calculator, orchestrator), config template, test commands, file layout.

**plan.md**: Architecture diagram, 10 design decisions, 6-phase delivery plan, test strategy (5 unit test files), Constitution Check (all PASS), risks.

**Source structure**: `src/analysis/` — 5 new files + `__init__.py`. Zero new dependencies. No MT5 imports in analysis module.

## Outcome

- ✅ Impact: Plan complete — `src/analysis/` fully designed; bridges gap between OHLCV data and volatility_filter + lot_calculator
- 🧪 Tests: 5 unit test files planned (test_atr_models, test_atr_calculator, test_reference_atr, test_adaptive_multipliers, test_atr_service); target ≥ 80% coverage
- 📁 Files: plan.md, research.md, data-model.md, quickstart.md, contracts/atr_service.md
- 🔁 Next prompts: /sp.tasks → /sp.implement
- 🧠 Reflection: Key insight — keeping ATRService pure (no MT5 calls) enables full unit test coverage without any broker mock, consistent with the pattern established across all existing modules. The None-not-zero contract for insufficient data prevents silent division-by-zero errors in lot_calculator.

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): Constitution Check — all 8 items PASS
- Prompt variant (if applicable): n/a
- Next experiment: Verify Timeframe enum MT5 constant values (5, 16385, 16388, 16408) against live MT5 Python package in integration test
