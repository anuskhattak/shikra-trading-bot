---
id: PHR-0024
title: risk-management-plan-review
stage: plan
date: 2026-05-16
surface: claude-code
model: claude-sonnet-4-6
feature: 003-risk-management
branch: 002-smc-engine
user: anaskhattak
command: /sp.plan specs/003-risk-management
labels: [plan, risk-management, artifacts-review, consistency-fix]
links:
  spec: specs/003-risk-management/spec.md
  ticket: ""
  adr: ""
  pr: ""
files:
  - specs/003-risk-management/plan.md
  - specs/003-risk-management/research.md
  - specs/003-risk-management/data-model.md
  - specs/003-risk-management/contracts/risk_manager.md
  - specs/003-risk-management/quickstart.md
tests:
  - ""
---

## Prompt

Generate the plan only for specs/003-risk-management

## Response snapshot

All Phase 0 and Phase 1 planning artifacts for spec003 already existed and were complete:
- `research.md` — XAUUSD pip value derivation, lot formula, ATR-based SL rationale, recovery mode rationale, session tracking logic
- `data-model.md` — Enums, RiskCalculation, RiskState, TradeAllowedResult dataclasses, config schema, log entry format
- `contracts/risk_manager.md` — Full public interface signatures for all 5 modules
- `quickstart.md` — 6-step integration guide with code examples

One consistency fix applied:
- `contracts/risk_manager.md` Zero Risk Calculation had `sl_distance_pips=0.0` — renamed to `sl_distance=0.0` to match spec clarification and data-model.md

`plan.md` status updated: Draft → Ready

Note: setup-plan.ps1 and update-agent-context.ps1 detected branch 002-smc-engine instead of 003-risk-management — scripts are branch-aware, not argument-aware; manual path override used.

## Outcome

- ✅ Impact: plan.md status set to Ready; naming inconsistency fixed across contracts/
- 🧪 Tests: N/A — planning artifacts, no code changed
- 📁 Files: contracts/risk_manager.md (sl_distance fix), plan.md (status update)
- 🔁 Next prompts: sp.tasks for spec003, then sp.implement
- 🧠 Reflection: setup-plan.ps1 always reads current git branch — does not support --feature flag; workaround is to checkout 003-risk-management branch before running, or use manual paths as done here

## Evaluation notes (flywheel)

- Failure modes observed: Both setup-plan.ps1 and update-agent-context.ps1 auto-detect branch and cannot be overridden via CLI args — they always target current branch (002-smc-engine)
- Graders run and results (PASS/FAIL): N/A
- Prompt variant (if applicable): N/A
- Next experiment: Consider adding -FeatureDir flag to powershell scripts for multi-branch workflows
