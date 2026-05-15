---
id: PHR-0017
title: Phase 5 Order Block Detection
stage: green
date: 2026-05-15
surface: agent
model: claude-sonnet-4-6
feature: 002-smc-engine
branch: 001-mt5-broker
user: anaskhattak
command: /sp.phr
labels: [order-block, ob, smc-engine, tdd, phase5, state-machine, unit-tests]
links:
  spec: specs/002-smc-engine/spec.md
  ticket: null
  adr: null
  pr: null
files:
  - src/engine/order_block.py
  - tests/unit/test_engine_order_block.py
  - specs/002-smc-engine/tasks.md
  - specs/002-smc-engine/checklists/implementation-review.md
tests:
  - tests/unit/test_engine_order_block.py (18 tests — all PASS)
---

## Prompt

phase5 implement karo

## Response snapshot

Phase 5 (User Story 3 — Order Block) ke dono tasks implement kiye: T014 ke liye 18 TDD-style failing tests likhe (test_engine_order_block.py — covering bullish/bearish OB detection, body-only boundaries, ACTIVE→TESTED→INVALIDATED state transitions, fast-move scenario, CHoCH support, edge cases), phir T015 ke liye src/engine/order_block.py mein detect_order_blocks() implement kiya. Sare 95 unit tests pass ho gaye, tasks.md T014/T015 checkmark, aur implementation-review CHK017-CHK022 + CHK057 complete.

## Outcome

- ✅ Impact: Phase 5 complete — Order Block detector fully implemented. detect_order_blocks(df, bos_type, bos_candle_index) backwards scan, body-only boundaries (FR-012), 3-state machine D-007 (ACTIVE/TESTED/INVALIDATED), CHoCH support sab implement. Progress: 35% → 47% (28/60 checklist items done).
- 🧪 Tests: 18 unit tests in test_engine_order_block.py — all PASS. Full suite: 95/95 PASS, no regressions.
- 📁 Files: src/engine/order_block.py (new), tests/unit/test_engine_order_block.py (new), specs/002-smc-engine/tasks.md (T014+T015 ✓), specs/002-smc-engine/checklists/implementation-review.md (CHK017–CHK022, CHK057 ✓)
- 🔁 Next prompts: Phase 6 (T016/T017) — Liquidity Sweep detection; then Phase 7 (T018–T022) — Scorer + Orchestrator
- 🧠 Reflection: State machine logic for OB needs careful handling of the "fast-move" case — when wick entry AND close-through happen in the same candle, TESTED is skipped and ACTIVE goes directly to INVALIDATED. The key insight: `low <= ob.top AND close < ob.bottom` in one candle = fast move, not a two-step transition.

## Evaluation notes (flywheel)

- Failure modes observed: create-phr.sh script missing — agent-native fallback used without issue. No functional failures in implementation.
- Graders run and results (PASS/FAIL): pytest tests/unit/test_engine_order_block.py → 18 PASS; pytest tests/unit/ → 95 PASS
- Prompt variant (if applicable): Minimal Hindustani instruction ("phase5 implement karo") — relies entirely on tasks.md context
- Next experiment (smallest change to try): Add a test for the case where the OB candle is directly adjacent to the BOS candle (bos_candle_index - 1 = 0) to ensure index boundary handling is explicit.
