---
id: PHR-0021
title: Spec003 Risk Management Spec Created
stage: spec
date: 2026-05-16
surface: agent
model: claude-sonnet-4-6
feature: 003-risk-management
branch: 001-mt5-broker
user: anaskhattak
command: /sp.phr
labels: ["spec003", "risk-management", "lot-sizing", "drawdown-guard", "recovery-mode", "spec"]
links:
  spec: specs/003-risk-management/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - specs/003-risk-management/spec.md
  - specs/003-risk-management/plan.md
  - specs/003-risk-management/data-model.md
  - specs/003-risk-management/tasks.md
  - specs/003-risk-management/quickstart.md
  - specs/003-risk-management/research.md
  - specs/003-risk-management/contracts/risk_manager.md
  - specs/003-risk-management/checklists/implementation-review.md
tests:
  - none
---

## Prompt

003-risk-management ke liya spec banao

## Response snapshot

Agent ne spec003 ka poora documentation set create kiya: spec.md (5 user stories, 27 FRs, 9 NFRs, 9 SCs), data-model.md (enums, dataclasses, config schema, XAUUSD pip reference), plan.md (7-phase delivery, 6-module architecture, 7 design decisions), tasks.md (18 tasks, T001–T018), contracts/risk_manager.md (public interface signatures + invariants), quickstart.md (6-step integration guide), research.md (XAUUSD contract specs, lot formula derivation, ATR vs fixed SL rationale), implementation-review.md (55 CHK items, all missing — implementation not started).

## Outcome

- ✅ Impact: Spec003 complete — 8 files, 55 CHK items defined. Risk module fully specced: lot_calculator, drawdown_guard, trade_limits, recovery_mode, risk_manager orchestrator. Pure-function, broker-agnostic, MT5-free design.
- 🧪 Tests: None yet — implementation not started
- 📁 Files: 8 spec artifacts created under `specs/003-risk-management/` and `history/prompts/003-risk-management/`
- 🔁 Next prompts: `003-risk-management ka Phase 1 implement karo` → T001–T004 (models + config)
- 🧠 Reflection: Risk management is the most critical module after the signal engine — incorrect lot sizing can blow the account even with a profitable signal strategy. Pure-function design (all state passed explicitly, no globals) makes testing trivial and ensures the risk module can be validated independently of MT5.

## Evaluation notes (flywheel)

- Failure modes observed: None — spec creation from existing documentation was straightforward.
- Graders run and results (PASS/FAIL): N/A — spec only, no tests.
- Next experiment: Consider splitting `evaluate_trade_risk` return into separate state-update calls to allow partial evaluation (e.g., check drawdown without computing lot size).
