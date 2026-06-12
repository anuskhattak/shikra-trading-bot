---
name: PHR-0070
title: spec007 Phase4 T024-T027 Pipeline Wiring
stage: green
date: 2026-06-12
surface: agent
model: claude-sonnet-4-6
feature: 007-h4-bias-engine
branch: 007-h4-bias-engine
user: anaskhattak
command: implement spec007 task.md phase4t024 to t027
labels: ["h4-bias", "pipeline", "run-pipeline", "backtest-engine", "strategy-orchestrator", "spec007", "stage0"]
links_spec: specs/007-h4-bias-engine/spec.md
links_ticket: null
links_adr: null
links_pr: null
files:
  - src/orchestrator/pipeline.py
  - src/orchestrator/strategy_orchestrator.py
  - src/backtest/backtest_engine.py
  - specs/007-h4-bias-engine/tasks.md
tests:
  - tests/unit/test_h4_bias.py (5 pass)
---

## Prompt

implement spec007 task.md phase4t024 to t027

## Response

Implemented Phase 4 tasks T024–T027 for spec007 H4 Bias Engine — wired `H4BiasService` into the shared pipeline and all callers:

- **T024** (`pipeline.py`): Added `h4_bias_service: H4BiasService | None = None` as optional 4th parameter to `run_pipeline()`. Default `None` preserves backward compatibility. Updated both callers (`backtest_engine.py`, `strategy_orchestrator.py`).
- **T025** (`pipeline.py`): Added Stage 0 before ATR refresh — calls `h4_bias_service.refresh(ctx.bars.get(Timeframe.H4, []))` and stores result in `ctx.h4_bias_result`. Guarded by `if h4_bias_service is not None`.
- **T026** (`pipeline.py`): Stage 2 now reads `ctx.h4_bias_result.bias` / `.strength` instead of hardcoded `Bias.NEUTRAL` / `0.0`, passing live H4 classification to `generate_signal()` and down to `score_and_assemble()`.
- **T027** (`backtest_engine.py`): Instantiated `H4BiasService(config)` as `self._h4_bias_service` in `BacktestEngine.__init__()`; passed to every `run_pipeline()` call in the bar loop.
- **Caller update** (`strategy_orchestrator.py`): `H4BiasService(config)` created in `StrategyOrchestrator.__init__()`; passed to `run_pipeline()` in `_on_new_bar()`.

All 5 existing `test_h4_bias.py` tests pass. Import smoke-test confirmed no circular imports.

## Outcome

Phase 4 pipeline wiring complete. `run_pipeline()` now executes 5 stages (Stage 0 = H4 bias refresh). Live H4 bias flows into every SMC signal decision in both backtest and live modes. T028–T030 (tests) remain to be written.

## Tests Summary

- `pytest tests/unit/test_h4_bias.py`: 5/5 pass
- `python -c "from src.orchestrator.pipeline import run_pipeline; from src.backtest.backtest_engine import BacktestEngine"`: imports OK

## Files Modified

- `src/orchestrator/pipeline.py`: added H4BiasService import, Stage 0 refresh, `h4_bias_service` param, live bias in Stage 2
- `src/orchestrator/strategy_orchestrator.py`: added H4BiasService import + `self._h4_bias_service`, updated `run_pipeline()` call
- `src/backtest/backtest_engine.py`: added H4BiasService import + `self._h4_bias_service`, updated `run_pipeline()` call
- `specs/007-h4-bias-engine/tasks.md`: T024–T027 marked `[x]`

## Next Prompts

- `implement phase4 t028 to t030` — Phase 4 tests: alignment boost, MTF multiplier, pipeline wiring assertions
- `implement phase5 t031 t032` — bias transition logging + audit fields test

## Reflection

Using `h4_bias_service: H4BiasService | None = None` (optional with default) was the right choice — it lets existing tests that call `run_pipeline()` directly continue working without any fixture changes. Stage 0 is a guard-checked `if` rather than an always-required stage so the pipeline degrades gracefully if no bias service is wired (e.g., in unit tests for other modules).

---

**Failure modes observed:** None — the `rg` (ripgrep) binary was absent in the shell environment, causing `Grep` tool errors; worked around with `Read` + manual inspection.

**Next experiment:** T028–T030 will numerically validate the alignment boost and MTF multiplier through the full `run_pipeline()` call rather than just `score_and_assemble()` isolation.
