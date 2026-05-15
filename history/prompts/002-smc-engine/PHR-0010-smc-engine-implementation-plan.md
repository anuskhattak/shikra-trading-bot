---
id: PHR-0010
title: SMC Engine Implementation Plan
stage: plan
date: 2026-05-12
surface: claude-code
model: claude-sonnet-4-6
feature: 002-smc-engine
branch: 001-mt5-broker
user: wshahrukh0@gmail.com
command: /sp.plan for 002-smc spec
labels: [plan, smc-engine, design, data-model, contracts]
links:
  spec: specs/002-smc-engine/spec.md
  ticket: ~
  adr: ~
  pr: ~
files:
  - specs/002-smc-engine/plan.md
  - specs/002-smc-engine/research.md
  - specs/002-smc-engine/data-model.md
  - specs/002-smc-engine/quickstart.md
  - specs/002-smc-engine/contracts/smc_engine.md
tests: ~
---

## Prompt

/sp.plan for 002-smc spec — generate full implementation plan for the SMC Signal Detection Engine.

## Response snapshot

**Phase 0 — Research (research.md)**: 8 research items resolved:
- R-001: Fractal swing detection — vectorized pandas shift() pattern
- R-002: BOS/CHoCH candle-close rule implementation
- R-003: FVG 3-candle vectorized scan + fill check
- R-004: OB TESTED status defined (wick → TESTED, close-through → INVALIDATED)
- R-005: "Established trend" = most recent confirmed BOS direction
- R-006: Confidence scoring — additive sum, weights sum=1.0 invariant
- R-007: false_signals.json thread safety — threading.Lock pattern
- R-008: Performance validated — 200 candles ≈ 3ms (100ms budget has 30× headroom)

**Phase 1 — Design (data-model.md)**: 11 entities defined:
- 6 enums: Bias, Direction, SignalType, FVGStatus, OBStatus, SweepType
- 5 dataclasses: SwingPoint, FVGZone, OrderBlock, LiquiditySweep, EntrySignal
- State transition tables for FVGZone and OrderBlock
- config.yaml schema with all configurable parameters

**Phase 1 — Contracts (contracts/smc_engine.md)**: Python public interface:
- `generate_signal(df, htf_bias, config) → EntrySignal` — single public entry point
- 5 internal module function signatures with full docstrings
- DataFrame input contract (columns, types, ordering)
- Guaranteed invariants table

**Phase 1 — Quickstart (quickstart.md)**: Live MT5 usage + synthetic DataFrame testing examples

**Source structure decided**: src/engine/ with 8 files — one per SMC concept + orchestrator

**8 design decisions documented** in plan.md (D-001 to D-008)

## Outcome

- ✅ Impact: Full implementation blueprint ready for /sp.tasks
- 🧪 Tests: Synthetic DataFrame test pattern shown in quickstart.md
- 📁 Files: plan.md, research.md, data-model.md, quickstart.md, contracts/smc_engine.md
- 🔁 Next prompts: /sp.tasks — generate actionable task list
- 🧠 Reflection: Separating each SMC concept into its own module (one-concept-one-file) is the key design decision — it maps directly to User Stories and enables independent unit testing

## Evaluation notes (flywheel)

- Failure modes observed: setup-plan.ps1 returns 001-mt5-broker paths (wrong branch) — worked around by using 002-smc-engine paths directly
- Graders run and results (PASS/FAIL): ~
- Prompt variant (if applicable): ~
- Next experiment: ~
