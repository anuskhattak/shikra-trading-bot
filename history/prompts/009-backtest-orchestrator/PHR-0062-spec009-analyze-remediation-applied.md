---
id: PHR-0062
title: spec009-analyze-remediation-applied
stage: misc
date: 2026-06-12
surface: claude-code
model: claude-sonnet-4-6
feature: 009-backtest-orchestrator
branch: 009-backtest-orchestrator
user: anaskhattak
command: /sp.analyze remediation
labels: [analyze, remediation, consistency-fix]
links:
  spec: specs/009-backtest-orchestrator/spec.md
  ticket: ""
  adr: ""
  pr: ""
files:
  - specs/009-backtest-orchestrator/spec.md
  - specs/009-backtest-orchestrator/tasks.md
tests:
  - n/a (artifact fixes only)
---

## Prompt

remediation apply karo (apply remediation from /sp.analyze findings)

## Response snapshot

Applied 7 fixes to spec.md and tasks.md based on /sp.analyze findings (PHR-0061). Fixes: (I1) spec.md edge case "14 H1 bars" corrected to "35 H1 bars" (period=14 + reference_period=20 + 1). (A1) T003 now includes orchestrator config section with max_reconnect_retries and reconnect_backoff_base_seconds. (U2) T010 _on_new_bar type comparison fixed: ctx.filter_result.final_result == FilterResult.ALLOWED instead of ctx.filter_result == ALLOWED. (U3) T010 now specifies current_price source: mt5.symbol_info_tick("XAUUSD").last. (D1) T010 clarifies daily drawdown is delegated to ExecutionEngine.run_preflight() — no duplicate check. (C3) T011 expanded from 4 to 5 tests — adds MT5ConnectionError reconnection test. (U1) T023 Sharpe formula now specifies bar_dates parallel list for calendar-day grouping. (U4) T005 now creates both PipelineContext and BarEvent dataclasses. (C1/C2) T029/T030 mark SC-002 and SC-003 as manual verification items with explicit instructions.
