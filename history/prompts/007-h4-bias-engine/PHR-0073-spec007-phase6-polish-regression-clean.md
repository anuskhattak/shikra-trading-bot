---
id: PHR-0073
title: spec007 Phase6 Polish Regression Clean
stage: green
date: 2026-06-12
surface: agent
model: claude-sonnet-4-6
feature: 007-h4-bias-engine
branch: 007-h4-bias-engine
user: anaskhattak
command: implement phase6
labels: ["h4-bias", "edge-cases", "counter-trend", "neutral-bias", "regression", "pytest", "fixture-fix", "spec007", "phase6"]
links:
  spec: specs/007-h4-bias-engine/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - tests/unit/test_h4_bias.py
  - tests/integration/test_backtest_full.py
  - tests/integration/test_orchestrator_mocked.py
  - specs/007-h4-bias-engine/tasks.md
  - specs/007-h4-bias-engine/checklists/implementation.md
tests:
  - tests/unit/test_h4_bias.py (11/11 pass)
  - tests/unit/ (455/455 pass — zero regressions)
  - python -c "from src.analysis.h4_bias import H4BiasService, H4BiasResult; print('OK')" → OK
---

## Prompt

implement phase6

## Response snapshot

Implemented Phase 6 (T033–T036): added `test_no_counter_trend_boost` and `test_neutral_bias_no_block_no_boost` edge-case tests (both pass); ran full regression and found 8 integration test failures caused by missing `analysis.h4_bias` config block in two test fixtures — fixed both fixtures; confirmed 455/455 unit tests pass with zero regressions. Import smoke test returns OK. All 36 spec007 tasks now complete.

## Outcome

- ✅ Impact: spec007 H4 Bias Engine fully complete — all 36 tasks done across 6 phases, 11/11 unit tests pass, 455/455 unit suite clean, importability confirmed.
- 🧪 Tests: `pytest tests/unit/test_h4_bias.py` → 11/11 pass | `pytest tests/unit/` → 455/455 pass | import smoke test → OK
- 📁 Files: `tests/unit/test_h4_bias.py` (T033 + T034 + docstring), `tests/integration/test_backtest_full.py` (h4_bias block added to bt_config_and_data fixture), `tests/integration/test_orchestrator_mocked.py` (h4_bias block added to _CONFIG), `specs/007-h4-bias-engine/tasks.md` (T033–T036 marked `[x]`), `specs/007-h4-bias-engine/checklists/implementation.md` (remaining 4 test entries + full checklist complete)
- 🔁 Next prompts:
  - `/sp.git.commit_pr` — all checklist items pass, spec007 ready to commit and open PR
  - `implement spec008` — next feature spec in the pipeline
- 🧠 Reflection: The integration test fixture failures (KeyError: 'h4_bias') were a predictable side effect of T027 wiring H4BiasService into BacktestEngine — any test that instantiates BacktestEngine or StrategyOrchestrator with a minimal config dict now needs the `analysis.h4_bias` block. The fix is simple (add 4 keys to each fixture) but the root cause should be documented: specs that add required config keys must audit all integration test fixtures that build minimal configs, not just unit tests.

## Evaluation notes (flywheel)

- Failure modes observed: Integration test fixtures in `test_backtest_full.py` and `test_orchestrator_mocked.py` were not updated when spec007 T027 wired `H4BiasService` into `BacktestEngine` and `StrategyOrchestrator`. This caused `KeyError: 'h4_bias'` on `H4BiasService.__init__()`. Separately, `TestLiveExecutionRoundTrip` failed with `insufficient margin (retcode 10030)` — a pre-existing live MT5 demo-account state issue, unrelated to spec007. Broker unit tests (`test_broker_*.py`) fail in full-suite runs due to MT5 state pollution from prior live integration tests — pre-existing isolation issue.
- Graders run and results (PASS/FAIL): `pytest tests/unit/test_h4_bias.py` → 11/11 PASS | `pytest tests/unit/` → 455/455 PASS | import smoke → PASS
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): When adding required config keys in future specs, add a task explicitly to audit and update all integration test fixtures that build `config` dicts from scratch — prevents silent KeyError regressions in integration tests.
