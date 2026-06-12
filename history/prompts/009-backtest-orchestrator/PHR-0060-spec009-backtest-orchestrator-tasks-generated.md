---
id: PHR-0060
title: spec009-backtest-orchestrator-tasks-generated
stage: tasks
date: 2026-06-12
surface: claude-code
model: claude-sonnet-4-6
feature: 009-backtest-orchestrator
branch: 009-backtest-orchestrator
user: anaskhattak
command: /sp.tasks
labels: [tasks, orchestrator, backtest, pipeline, tdd]
links:
  spec: specs/009-backtest-orchestrator/spec.md
  ticket: ""
  adr: ""
  pr: ""
files:
  - specs/009-backtest-orchestrator/tasks.md
tests:
  - tests/unit/test_pipeline.py
  - tests/unit/test_bar_monitor.py
  - tests/unit/test_backtest_models.py
  - tests/unit/test_data_loader.py
  - tests/unit/test_position_simulator.py
  - tests/unit/test_performance.py
  - tests/integration/test_orchestrator_mocked.py
  - tests/integration/test_backtest_full.py
---

## Prompt

/sp.tasks (for feature 009-backtest-orchestrator)

## Response snapshot

Generated 30 tasks (T001–T030) across 6 phases for spec009 Backtest Suite & Strategy Orchestrator. Phase 1 (Setup): 4 tasks — directories, pandas dep, config, data dirs. Phase 2 (Foundational): 3 tasks — PipelineContext model, run_pipeline() shared core, test_pipeline.py. Phase 3 (US1 Live Orchestrator, P1): 5 tasks — bar_monitor.py + tests, strategy_orchestrator.py + integration test, main.py. Phase 4 (US2 Backtest Engine, P1): 9 tasks — SimulatedPosition/TradeRecord models, data_loader, position_simulator, signal_exporter, BacktestEngine.run(), integration test — all parallel streams (A/B/C/D). Phase 5 (US3 Performance Report, P2): 5 tasks — PerformanceMetrics/BacktestResult models, compute_metrics(), test_performance.py, BacktestEngine integration, backtest_runner.py CLI. Phase 6 (Polish): 4 tasks — exports, coverage gate (≥ 80%), smoke test. US1 and US2 are fully parallel after Phase 2 (zero shared source files).
