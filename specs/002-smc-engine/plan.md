# Implementation Plan: SMC Signal Detection Engine

**Branch**: `002-smc-engine` | **Date**: 2026-05-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/002-smc-engine/spec.md`

---

## Summary

Build a pure Python, stateless SMC (Smart Money Concepts) signal detection engine that processes XAUUSD H1 OHLCV candle DataFrames and produces a single scored `EntrySignal`. The engine detects five institutional price patterns (BOS, CHoCH, FVG, Order Block, Liquidity Sweep), combines them into a confidence score (0.0–1.0), and returns a human-readable signal. Every discarded signal is logged to `logs/false_signals.json`. No MT5 connection required — engine is broker-agnostic and operates purely on pandas DataFrames.

---

## Technical Context

**Language/Version**: Python 3.10+
**Primary Dependencies**: pandas ≥ 2.0, numpy ≥ 1.24, loguru (logging), pyyaml (config weights)
**Storage**: `logs/false_signals.json` — append-only, file-based audit log (no database)
**Testing**: pytest + pytest-cov (unit tests with synthetic candle DataFrames)
**Target Platform**: Windows 10, same machine as MT5 terminal
**Project Type**: Single Python library module (`src/engine/`)
**Performance Goals**: < 100ms for full signal generation on 200 H1 candles (SC-005)
**Constraints**: Stateless per signal call (NFR-002); no MT5 import in engine code (NFR-003); candle-close rule enforced throughout (FR-004, FR-007, FR-011)
**Scale/Scope**: 200 candles per call, single symbol (XAUUSD), single timeframe (H1)

---

## Constitution Check

*GATE: Must pass before Phase 0 research.*

| Gate | Status | Notes |
|------|--------|-------|
| No new external broker dependency | ✅ PASS | Engine is broker-agnostic — only pandas/numpy |
| No hardcoded credentials or secrets | ✅ PASS | Confidence weights via config.yaml |
| Risk controls enforced | ✅ PASS | Low-confidence signals discarded via threshold (FR-019) |
| All signals produce confidence scores | ✅ PASS | FR-017/FR-018 enforced |
| Signal decisions logged | ✅ PASS | FR-023 — false_signals.json |
| Unit test coverage target ≥ 80% | ✅ PASS | SC-008 — 5 detection functions |
| No live trading without backtest | ✅ PASS | Engine is detection-only; no order placement |

**Verdict**: All gates pass. Proceed to Phase 0.

---

## Project Structure

### Documentation (this feature)

```text
specs/002-smc-engine/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/           ← Phase 1 output
│   └── smc_engine.md
└── tasks.md             ← Phase 2 output (/sp.tasks command)
```

### Source Code (repository root)

```text
src/engine/
├── __init__.py              ← public exports: generate_signal, EntrySignal, Bias
├── models.py                ← all dataclasses and enums
├── swing.py                 ← fractal swing point detection (FR-001)
├── bos_choch.py             ← BOS / CHoCH detection (FR-002, FR-003, FR-004)
├── fvg.py                   ← Fair Value Gap detection (FR-005 to FR-008)
├── order_block.py           ← Order Block detection (FR-009 to FR-012)
├── liquidity_sweep.py       ← Liquidity Sweep detection (FR-013 to FR-016)
├── scorer.py                ← confidence scoring + EntrySignal assembly (FR-017 to FR-022)
└── smc_engine.py            ← top-level orchestrator — single public entry point

tests/unit/
├── test_engine_swing.py
├── test_engine_bos_choch.py
├── test_engine_fvg.py
├── test_engine_order_block.py
├── test_engine_liquidity_sweep.py
├── test_engine_scorer.py
└── test_engine_smc_engine.py   ← full pipeline test: BOS+FVG+OB → EntrySignal (US5)

logs/
└── false_signals.json       ← append-only audit log (gitignored)

config.yaml                  ← smc_engine section added (fractal_n, weights, threshold, min_candles)
```

**Structure Decision**: Single library module under `src/engine/`. Each SMC concept gets its own file — this matches the five User Stories and enables independent unit testing per detector. The orchestrator `smc_engine.py` is the only public entry point that downstream modules (risk manager, order executor) import.

---

## Design Decisions

### D-001: One module per SMC concept
Each of the five detectors (swing, BOS/CHoCH, FVG, OB, LS) is a standalone pure function module. No class hierarchy. Every function takes a DataFrame and returns a result — no side effects except the scorer's `false_signals.json` write.

**Why**: Isolation enables independent unit testing with synthetic DataFrames. Adding a new SMC concept = adding one file without touching others.

### D-002: Stateless per call — full recompute
On every call, the engine recomputes all swing points, FVGs, and OBs from scratch from the candles passed in. No instance-level cache.

**Why**: Enables trivially parallel backtesting (multiple threads, same engine). No stale state bugs. Confirmed in Clarifications Q1.

### D-003: Candle-close rule everywhere
BOS/CHoCH, FVG fill, and OB invalidation all use the same candle-close rule — wick entries don't count.

**Why**: Eliminates false triggers from wicks. Consistent with original Shikra EA v10. Confirmed in Clarifications Q4.

### D-004: OB body = entry_zone (primary)
When an Order Block is detected and aligned, `EntrySignal.entry_zone` uses the OB body boundaries. FVG is fallback when no OB present.

**Why**: OB provides the most precise institutional entry level. Confirmed in Clarifications Q5.

### D-005: Confidence scoring — additive weighted sum
`confidence = sum(weight_i for each present component)`. Missing component contributes 0. Weights are config-driven (config.yaml). Default: BOS=0.40, FVG=0.30, OB=0.20, LS=0.10.

**Why**: Simple, deterministic, auditable. SC-006 (deterministic) satisfied trivially.

### D-006: "Established trend" defined as last confirmed BOS direction
CHoCH requires an established trend. Definition: the most recent confirmed BOS determines current trend. If last BOS = BOS_BULLISH → current trend = bullish. CHoCH fires when price closes below the most recent swing low of that trend.

**Why**: Derived naturally from the swing/BOS tracking already required by FR-001/FR-002.

### D-007: OB TESTED status — wick entry rule (exception to D-003)
OB ACTIVE → TESTED: triggered when a candle **wick** enters the OB zone (price touched it).
OB TESTED → INVALIDATED: triggered when a candle **closes** through the OB body.

**Why**: TESTED is an informational flag (price reached the zone); INVALIDATED is a structural decision (zone destroyed). Different semantics warrant different rules.

### D-008: NFR-002 "stateless" scoped to signal computation
"Stateless" means no in-memory signal state between calls. File writes to `false_signals.json` are an explicit audit side effect — not a violation of NFR-002.

**Why**: Resolves the spec conflict (CHK015). Logging is a cross-cutting concern, not signal state.

### D-009: News spike single-candle BOS — no extra confirmation step
A BOS or CHoCH triggered by a single extreme candle (news spike) is handled entirely by the candle-close rule (D-003) — wick-only moves are already rejected because detection compares `df['close']`, not `df['high']`/`df['low']`. No "next candle confirmation" logic is added.

**Why**: Additional confirmation would require remembering a "pending signal" across calls — directly violating NFR-002 (stateless). News spike filtering is deferred to the ML confidence filter (Spec 008). The candle-close rule is the primary guard per FR-004.

---

## Complexity Tracking

No constitution violations. No complexity justification needed.
