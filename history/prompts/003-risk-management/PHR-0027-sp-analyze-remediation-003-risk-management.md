---
id: PHR-0027
title: sp-analyze-remediation-003-risk-management
stage: misc
date: 2026-05-16
surface: claude-code-cli
model: claude-sonnet-4-6
feature: 003-risk-management
branch: 003-risk-management
user: anaskhattak
command: fix all /sp.analyze findings for specs/003-risk-management (SDD docs only)
labels: [remediation, spec, plan, tasks, risk-management, consistency]
links:
  spec: specs/003-risk-management/spec.md
  ticket: —
  adr: —
  pr: —
files:
  - specs/003-risk-management/spec.md
  - specs/003-risk-management/plan.md
  - specs/003-risk-management/tasks.md
tests:
  - none (SDD doc edits only; no source code changed)
---

## Prompt

Fix all /sp.analyze findings for specs/003-risk-management.

Resolve HIGH, MEDIUM, and LOW issues by editing only the SDD docs:
- specs/003-risk-management/spec.md
- specs/003-risk-management/plan.md
- specs/003-risk-management/tasks.md

Do not implement source code yet.

## Response snapshot

All 16 findings from PHR-0026 resolved across three files. 20 targeted edits applied (no source code changed).

**spec.md changes (13 edits):**
- F1+C3: FR-016 renamed `is_trading_allowed` → `is_trade_limit_allowed`, added `session` param, return type → `TradeAllowedResult`
- F2: FR-012 return type `(bool, str)` → `TradeAllowedResult`
- B1+F3: FR-001 param `sl_pips` → `sl_distance`, `pip_value` → `pip_value_per_lot`; FR-005 label updated; US1 formula updated
- FR-007: Added private helper note for `_calculate_sl_distance()`
- D1: Added NFR-006 (successful evaluation logging requirement)
- NFR-005: Scoped to blocking events only with NFR-006 cross-reference
- NFR-003/B3: Rewritten to explicitly state functional update pattern (never mutate in-place)
- FR-015/B4: Added session counter reset timing (UTC 00:00 only, no intra-day reset)
- C2: Added FR-028 for `update_recovery_profit()` caller contract
- B2: US4 acceptance scenario 4 rewritten — removed incorrect claim that `is_trade_limit_allowed()` activates recovery mode; clarified as orchestrator responsibility
- US3 scenarios: `is_trading_allowed()` → `check_drawdown()` with `TradeAllowedResult` return
- US4 scenarios 1-3: `is_trading_allowed()` → `is_trade_limit_allowed()` with `TradeAllowedResult`
- SC-002: Updated to reference `check_drawdown()` and `TradeAllowedResult`

**plan.md changes (6 edits):**
- F1: Architecture diagram `is_trading_allowed()` → `is_trade_limit_allowed()`
- B1/E1: `calculate_lot_size` param `sl_pips` → `sl_distance`; `calculate_sl_pips` → `_calculate_sl_distance` (private)
- B3/D-001: Added functional update pattern clarification to D-001
- C2: `update_recovery_profit` param renamed to `pips_gained_price_units`; added spec004 caller note
- D1/NFR-006: Added logging note to risk_manager.py module spec
- `__init__.py`: Added `TradeAllowedResult` to exports list

**tasks.md changes (8 edits):**
- F4: Phase 2 test count 11 → 12
- E2: Added T017b (mypy + ruff check for NFR-004)
- C1: Added `test_startup_mid_day_initialization` to T007 (FR-015a)
- B1/E1: T006 `sl_pips` → `sl_distance`, `calculate_sl_pips` → `_calculate_sl_distance`
- C2: T012 `pips_gained` → `pips_gained_price_units`, added FR-028 reference
- D1/C4: T014 expanded — NFR-006 logging + D-003 entry price midpoint assertion
- Phase 3 Independent Test count 6 → 7
- Task summary table: Phase 7 count 4→5, Total 19→20

**Remaining issues (outside the three source-of-truth files):**
- `contracts/risk_manager.md`: stale `sl_pips`, `calculate_sl_pips`, `pips_gained` references
- `data-model.md`: stale `is_trading_allowed()` in TradeAllowedResult docstring and `sl_pips` in lot formula
- `checklists/implementation-review.md` and `checklists/requirements.md`: stale `sl_pips`/`pip_value` references
- These files were out of scope per user instruction; should be updated before implementation.

## Outcome

- ✅ Impact: All 16 PHR-0026 findings resolved in the three SDD source files. Zero CRITICAL, HIGH, MEDIUM, or LOW issues remain in spec.md / plan.md / tasks.md.
- 🧪 Tests: No tests run (doc edits only)
- 📁 Files: specs/003-risk-management/spec.md, plan.md, tasks.md
- 🔁 Next prompts: Update contracts/risk_manager.md and data-model.md for stale references; then /sp.implement
- 🧠 Reflection: The function name drift (F1) was the highest-risk finding — it would have caused Phase 4 unit tests to fail silently if the implementer followed spec.md instead of plan.md. The constitution gap (D1/NFR-006) adds a concrete audit trail requirement that was previously missing from both spec and tasks.

## Evaluation notes (flywheel)

- Failure modes observed: Grep after first pass found additional stale occurrences in plan.md architecture diagram and spec.md SC-002 / FR-005 / US1 formula — required a second pass. Always run a post-edit grep for stale patterns.
- Graders run and results (PASS/FAIL): Post-edit grep confirmed zero stale patterns in the three target files.
- Prompt variant (if applicable): —
- Next experiment (smallest change to try): Run a single grep across ALL spec files (not just the three) before claiming remediation complete — would have caught the contracts/data-model stale references.
