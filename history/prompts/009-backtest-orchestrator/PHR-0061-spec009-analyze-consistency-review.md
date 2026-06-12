---
id: PHR-0061
title: spec009-analyze-consistency-review
stage: misc
date: 2026-06-12
surface: claude-code
model: claude-sonnet-4-6
feature: 009-backtest-orchestrator
branch: 009-backtest-orchestrator
user: anaskhattak
command: /sp.analyze
labels: [analyze, consistency, review, pre-implementation]
links:
  spec: specs/009-backtest-orchestrator/spec.md
  ticket: ""
  adr: ""
  pr: ""
files:
  - specs/009-backtest-orchestrator/spec.md
  - specs/009-backtest-orchestrator/plan.md
  - specs/009-backtest-orchestrator/tasks.md
tests:
  - n/a (read-only analysis)
---

## Prompt

/sp.analyze (for feature 009-backtest-orchestrator)

## Response snapshot

Read-only analysis of spec.md + plan.md + tasks.md. Found 13 issues: 0 CRITICAL, 4 HIGH, 6 MEDIUM, 3 LOW. No constitution violations. Coverage: 22/27 requirements fully covered (81%); 4 partial; 2 zero (SC-002 pipeline timing, SC-003 backtest timing — both performance-only, no unit test possible). HIGH issues: (1) SC-002/SC-003 have no task coverage — mark as manual verification; (2) Sharpe calculation underspecified — equity_curve is per-H1-bar but Sharpe requires per-calendar-day aggregation, grouping logic missing from T023; (3) Spec edge case says "14 H1 bars" ATR warm-up but actual is 35 bars — misleading. MEDIUM issues: FR-008 reconnect retries config key missing (A1), type comparison bug in T010 _on_new_bar (U2), current_price source for manage_open_positions missing (U3), daily drawdown may duplicate spec005 preflight (D1), BarEvent entity has no instantiation task (U4), reconnection test missing from T011 (C3). Remediation offered for top 4 HIGH issues.
