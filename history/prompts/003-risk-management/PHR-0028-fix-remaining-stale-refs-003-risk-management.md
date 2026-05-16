---
id: PHR-0028
title: fix-remaining-stale-refs-003-risk-management
stage: misc
date: 2026-05-16
surface: claude-code-cli
model: claude-sonnet-4-6
feature: 003-risk-management
branch: 003-risk-management
user: anaskhattak
command: yes, fix those too (remaining stale references in contracts, data-model, checklists, research)
labels: [remediation, contracts, data-model, checklists, consistency]
links:
  spec: specs/003-risk-management/spec.md
  ticket: —
  adr: —
  pr: —
files:
  - specs/003-risk-management/contracts/risk_manager.md
  - specs/003-risk-management/data-model.md
  - specs/003-risk-management/checklists/implementation-review.md
  - specs/003-risk-management/checklists/requirements.md
  - specs/003-risk-management/research.md
tests:
  - none (SDD doc edits only; no source code changed)
---

## Prompt

yes, fix those too
(referring to remaining stale references in contracts/risk_manager.md, data-model.md,
checklists/implementation-review.md, checklists/requirements.md identified in PHR-0027)

## Response snapshot

Fixed all stale references across 5 supporting files. 18 targeted edits applied.

**contracts/risk_manager.md (4 edits):**
- `state` comment: "mutable session state" → "session state — never mutate in place"
- `evaluate_trade_risk` docstring: added NFR-006 success logging note
- `calculate_lot_size`: param `sl_pips` → `sl_distance` with updated comment "price units"
- `calculate_sl_pips()` → `_calculate_sl_distance()`: renamed and updated docstring ("price units" not "pips")
- `update_recovery_profit`: param `pips_gained` → `pips_gained_price_units`; added FR-028 caller note

**data-model.md (4 edits):**
- `RiskState` heading: "Mutable session state" → "Session state (owned by caller; functions return new instances)"
- `TradeAllowedResult` heading: "Returned by `is_trading_allowed()`" → "Returned by `check_drawdown()` and `is_trade_limit_allowed()`"
- Lot formula: `sl_pips * pip_value_per_lot` → `sl_distance * pip_value_per_lot`
- Log Entry Format: added NFR-006 success event JSON example alongside existing blocking events

**checklists/implementation-review.md (5 edits):**
- CHK003: formula `sl_pips × pip_value` → `sl_distance × pip_value_per_lot`
- Added CHK029b for FR-028 (`update_recovery_profit` caller contract)
- Added CHK038b for NFR-006 (successful evaluation logging)
- CHK051: 11 → 12 tests; CHK052: 6 → 7 tests
- Summary table: Recovery 5→6, NFR 5→6, Total 55→57

**checklists/requirements.md (4 edits):**
- FR range for Recovery: FR-023–FR-027 → FR-023–FR-028
- RiskCalculation fields: `sl_distance_pips` → `sl_distance`
- Lot formula: `sl_pips` → `sl_distance` with "price units" note
- NFR-005 entry: added NFR-006 cross-reference for successful evaluation logging

**research.md (1 edit — bonus, not in original list):**
- Lot sizing formula derivation: `sl_pips` → `sl_distance`; added clarifying comment "price units (same as D1_ATR)"

**Post-edit verification:** grep across all 7 files — zero stale occurrences remain. Only intentional uses of `sl_distance_pips` remain in spec.md clarification Q&A (documenting the rename decision).

## Outcome

- ✅ Impact: All sp.analyze findings now fully propagated across every spec artifact. All 7 files in specs/003-risk-management/ are internally consistent. Ready for /sp.implement.
- 🧪 Tests: No tests run (doc edits only)
- 📁 Files: contracts/risk_manager.md, data-model.md, checklists/implementation-review.md, checklists/requirements.md, research.md
- 🔁 Next prompts: /sp.implement for specs/003-risk-management
- 🧠 Reflection: Stale references in supporting files (contracts, checklists) are often missed when spec/plan/tasks are updated. A post-edit grep across the entire feature directory — not just the three source-of-truth files — should be standard practice after any sp.analyze remediation pass.

## Evaluation notes (flywheel)

- Failure modes observed: research.md was not in the originally identified list but had a stale sl_pips formula — caught by the global grep sweep. Adding research.md to the grep scope was the right call.
- Graders run and results (PASS/FAIL): Post-edit grep confirmed zero stale patterns across all 7 files.
- Prompt variant (if applicable): —
- Next experiment: Include research.md and contracts/ in the sp.analyze grep scope by default in future analysis runs.
