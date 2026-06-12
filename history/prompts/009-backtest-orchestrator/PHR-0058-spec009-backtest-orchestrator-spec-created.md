---
id: PHR-0058
title: spec009-backtest-orchestrator-spec-created
stage: spec
date: 2026-06-12
surface: claude-code
model: claude-sonnet-4-6
feature: 009-backtest-orchestrator
branch: 009-backtest-orchestrator
user: anaskhattak
command: /sp.specify
labels: [spec, orchestrator, backtest, pipeline, trading-loop]
links:
  spec: specs/009-backtest-orchestrator/spec.md
  ticket: ""
  adr: ""
  pr: ""
files:
  - specs/009-backtest-orchestrator/spec.md
  - specs/009-backtest-orchestrator/checklists/requirements.md
tests:
  - n/a (spec stage)
---

## Prompt

/sp.specify spec009 — Backtest Suite + Strategy Orchestrator: A unified feature that (1) implements the main Strategy Orchestrator class tying all 6 existing modules together (broker/MT5 → ATR calibration → SMC signal engine → pre-trade filters → risk management → execution engine) into a single trading loop, and (2) implements a Backtest Engine that runs the same orchestrator logic over historical OHLCV data to produce performance metrics (Win%, Profit Factor, Sharpe Ratio, Max Drawdown). The orchestrator is the missing main.py entry point for XAUUSD Gold trading using Smart Money Concepts strategy on MetaTrader 5.

## Response snapshot

Created spec009 specification covering two P1 user stories (Live Strategy Orchestrator + Backtest Engine) and one P2 story (Performance Report). Defined 18 functional requirements (FR-001–FR-018) spanning orchestrator lifecycle, bar-event pipeline, backtest simulation, and shared pipeline core. Identified 7 key entities (StrategyOrchestrator, BacktestEngine, PipelineContext, SimulatedPosition, BacktestResult, TradeRecord, BarEvent) and 9 measurable success criteria. All quality checklist items passed — no NEEDS CLARIFICATION markers. Branch 009-backtest-orchestrator created.
