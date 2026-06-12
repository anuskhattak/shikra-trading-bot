---
id: PHR-0052
title: spec006-atr-calibration-spec-created
stage: spec
date: 2026-05-22
surface: claude-code
model: claude-sonnet-4-6
feature: 006-atr-calibration
branch: 006-atr-calibration
user: anaskhattak
command: /sp.specify
labels: [spec, atr, calibration, volatility, caching]
links:
  spec: specs/006-atr-calibration/spec.md
  ticket: ""
  adr: ""
  pr: ""
files:
  - specs/006-atr-calibration/spec.md
  - specs/006-atr-calibration/checklists/requirements.md
tests:
  - n/a (spec stage)
---

## Prompt

/sp.specify ATR Calibration Module (spec006) — Multi-timeframe ATR calculation (M5, H1, H4, D1) from OHLCV data, reference ATR computation for volatility filter, ATR-adaptive SL/TP multipliers that adjust based on volatility regime, and ATR caching with periodic refresh mechanism for XAUUSD Gold trading bot

## Response snapshot

Created spec006 for the ATR Calibration Module on branch `006-atr-calibration`. The spec defines:
- 4 user stories covering ATR computation, reference ATR for volatility filter, adaptive SL/TP multipliers by regime, and bar-close cache refresh
- 13 functional requirements (FR-001 to FR-013) covering True Range calculation, multi-TF ATR, reference ATR, adaptive multipliers, caching, error handling, and configurability
- 5 key entities: ATRReading, VolatilityRegime, AdaptiveMultipliers, ATRCache, OHLCVBar
- 7 measurable success criteria
- Full assumptions, edge cases, and out-of-scope sections
- Quality checklist created with all items passing

## Outcome

- ✅ Impact: Spec006 complete — ATR Calibration Module fully specified; feeds existing volatility_filter.py (spec004) and lot_calculator.py (spec003) with computed ATR values
- 🧪 Tests: No tests yet (spec stage); SC-006 targets ≥ 80% coverage at implementation
- 📁 Files: specs/006-atr-calibration/spec.md, specs/006-atr-calibration/checklists/requirements.md
- 🔁 Next prompts: /sp.clarify → /sp.plan → /sp.tasks → /sp.implement
- 🧠 Reflection: ATR module is the missing bridge between raw OHLCV data and the volatility filter + lot calculator — without it, both modules receive ATR as dead input parameters. Spec correctly scopes out H4 bias (spec007) to keep feature bounded.

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): Requirements checklist — all items PASS
- Prompt variant (if applicable): n/a
- Next experiment: Verify adaptive multiplier defaults (1.0/1.5/2.0× SL) against backtesting results once spec009 is complete
