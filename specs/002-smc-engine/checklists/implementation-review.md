# Implementation Review Checklist: SMC Signal Detection Engine

**Purpose**: Track which spec requirements are implemented in code vs missing — "kiya kaam kar raha hai or kiya nahi"
**Created**: 2026-05-14
**Feature**: [spec.md](../spec.md)
**Code Under Review**: `src/engine/swing.py`, `src/engine/bos_choch.py`, `src/engine/fvg.py`, `src/engine/order_block.py`, `src/engine/liquidity_sweep.py`, `src/engine/scorer.py`, `src/engine/smc_engine.py`, `src/engine/models.py`

**Legend**: `[x]` = Done | `[ ]` = Missing | `[~]` = Partial / Gap

---

## Models & Enums — `src/engine/models.py`

- [x] CHK001 — T005: All 6 enums defined — `Bias`, `Direction`, `SignalType`, `FVGStatus`, `OBStatus`, `SweepType` [Spec §Key Entities, data-model.md]
- [x] CHK002 — T006: All 5 dataclasses defined — `SwingPoint`, `FVGZone`, `OrderBlock`, `LiquiditySweep`, `EntrySignal` with correct field types [data-model.md §Entities]
- [~] CHK003 — T006: `EntrySignal` invariants documented in docstring ✅; runtime enforcement → Phase 7 (scorer.py / smc_engine.py) [Spec §FR-019, data-model.md §Invariants]

---

## Functional Requirements — Swing Point Detection (`src/engine/swing.py`)

- [x] CHK004 — T010/FR-001: `detect_swing_points()` implements fractal rule — N candles on each side with strictly lower highs (swing high) or higher lows (swing low) [Spec §FR-001]
- [x] CHK005 — T010/FR-001: Unconfirmed pivots excluded from output — last `fractal_n` rows always unconfirmed [Spec §FR-001, contracts/smc_engine.md §swing.py]
- [x] CHK006 — T010/NFR-001: Inline comments explain the fractal pivot rule in `swing.py` [Spec §NFR-001]

---

## Functional Requirements — BOS / CHoCH Detection (`src/engine/bos_choch.py`)

- [x] CHK007 — T011/FR-002: `detect_structure_break()` detects BOS when candle closes beyond most recent swing high (bullish) or swing low (bearish) [Spec §FR-002]
- [x] CHK008 — T011/FR-003: CHoCH detected when candle closes beyond swing low in established bullish trend (or swing high in bearish trend) [Spec §FR-003]
- [x] CHK009 — T011/FR-004: Candle-close rule enforced — `df['close']` used exclusively; wick moves never trigger BOS/CHoCH [Spec §FR-004, SC-001]
- [x] CHK010 — T011/D-006: "Established trend" derived from direction of most recent confirmed BOS [plan.md §D-006]
- [x] CHK011 — T011/NFR-001: Inline comments explain BOS rule, CHoCH rule, and why wicks are excluded [Spec §NFR-001]

---

## Functional Requirements — FVG Detection (`src/engine/fvg.py`)

- [x] CHK012 — T013/FR-005: Bullish FVG detected when `candle[N-2].high < candle[N].low` [Spec §FR-005]
- [x] CHK013 — T013/FR-006: Bearish FVG detected when `candle[N-2].low > candle[N].high` [Spec §FR-006]
- [x] CHK014 — T013/FR-007: Fill status uses candle-close rule — zone marked FILLED only when `candle.close` is inside zone; wick entries do not count [Spec §FR-007]
- [x] CHK015 — T013/FR-008: FVG boundaries recorded: `top`, `bottom`, `midpoint` [Spec §FR-008]
- [x] CHK016 — T013/NFR-001: Inline comments explain 3-candle gap rule and why wick fills are rejected [Spec §NFR-001]

---

## Functional Requirements — Order Block Detection (`src/engine/order_block.py`)

- [x] CHK017 — T015/FR-009: Bullish OB = last bearish candle (`close < open`) immediately before a bullish BOS [Spec §FR-009]
- [x] CHK018 — T015/FR-010: Bearish OB = last bullish candle (`close > open`) immediately before a bearish BOS [Spec §FR-010]
- [x] CHK019 — T015/FR-011: OB invalidated when candle closes through OB body in opposite direction (candle-close rule); wick penetration does NOT invalidate [Spec §FR-011]
- [x] CHK020 — T015/FR-012: OB boundaries use body only — `top = max(open, close)`, `bottom = min(open, close)`; wicks excluded [Spec §FR-012]
- [x] CHK021 — T015/D-007: TESTED triggered by wick entry (`candle.low <= ob.top`); INVALIDATED triggered by close-through [plan.md §D-007]
- [x] CHK022 — T015/NFR-001: Inline comments explain OB origin rule, TESTED vs INVALIDATED distinction, and body-only boundary logic [Spec §NFR-001]

---

## Functional Requirements — Liquidity Sweep Detection (`src/engine/liquidity_sweep.py`)

- [x] CHK023 — T017/FR-013: Equal highs detected when two or more candle highs within `pip_tolerance` ($0.50 default) [Spec §FR-013]
- [x] CHK024 — T017/FR-014: Sweep High detected when candle wicks above equal highs AND closes back below — same candle [Spec §FR-014]
- [x] CHK025 — T017/FR-015: Sweep Low detected when candle wicks below equal lows AND closes back above — same candle [Spec §FR-015]
- [x] CHK026 — T017/FR-016: `sweep_level` (equal high/low price) and `close_price` recorded for each sweep [Spec §FR-016]
- [x] CHK027 — T017/NFR-001: Inline comments explain stop-hunt mechanics and same-candle close rule [Spec §NFR-001]

---

## Functional Requirements — Scorer & Orchestrator (`src/engine/scorer.py`, `src/engine/smc_engine.py`)

- [x] CHK028 — T020/FR-017: `entry_zone` uses OB body (top/bottom) when active OB present; falls back to FVG boundaries when no OB [Spec §FR-017, plan.md §D-004]
- [x] CHK029 — T020/FR-018: Confidence = additive weighted sum of present components; default weights: BOS=0.40, FVG=0.30, OB=0.20, LS=0.10 [Spec §FR-018, plan.md §D-005]
- [x] CHK030 — T020/FR-019: Signals with `confidence < 0.65` discarded and logged to `logs/false_signals.json` with reason "Below confidence threshold" [Spec §FR-019]
- [x] CHK031 — T020/FR-020: `reason` string populated for every signal — e.g., `"BOS_BULLISH + FVG + OB + Liquidity Sweep"` [Spec §FR-020]
- [x] CHK032 — T021/FR-021: `htf_bias` filter applied — only signals matching bias direction generated; `NEUTRAL` = no filter [Spec §FR-021]
- [x] CHK033 — T021/FR-022: `generate_signal()` always returns valid `EntrySignal` — never `None`, never raises on valid DataFrame [Spec §FR-022]
- [x] CHK034 — T020/FR-023: Every discarded signal written to `logs/false_signals.json` with timestamp, reason, confidence score [Spec §FR-023]
- [x] CHK035 — T020/FR-024: Accepted `EntrySignal` includes `components` list for downstream audit [Spec §FR-024]
- [x] CHK036 — T021/NFR-002: Engine is stateless — no cross-call state; full recompute on every `generate_signal()` call [Spec §NFR-002]
- [x] CHK037 — T021/NFR-003: No `import MetaTrader5` in any `src/engine/` module [Spec §NFR-003]

---

## Non-Functional Requirements

- [x] CHK038 — NFR-001: All 5 detection functions have inline comments explaining SMC rule [Spec §NFR-001] *(enforced via T010, T011, T013, T015, T017)*
- [x] CHK039 — NFR-002: `generate_signal()` documented as stateless; no instance-level cache or mutable default args [Spec §NFR-002]
- [x] CHK040 — NFR-003: `grep -r "MetaTrader5\|import mt5" src/engine/` returns zero results [Spec §NFR-003]

---

## Success Criteria

- [x] CHK041 — SC-001: Unit test proves wick-only BOS/CHoCH move returns `SignalType.NONE` [Spec §SC-001, tests/unit/test_engine_bos_choch.py]
- [x] CHK042 — SC-002: FVG zone `top` and `bottom` match expected values to 2 decimal places in unit test [Spec §SC-002, tests/unit/test_engine_fvg.py]
- [ ] CHK043 — SC-003: Hand-labelled 200-candle XAUUSD H1 OB dataset — **DEFERRED** (no task assigned; post-implementation validation) [Spec §SC-003, Gap]
- [x] CHK044 — SC-004: Unit test confirms `LIQUIDITY_SWEEP_HIGH` detected within the same candle it occurs [Spec §SC-004, tests/unit/test_engine_liquidity_sweep.py]
- [x] CHK045 — SC-005: Benchmark test confirms `generate_signal()` on 200-row DataFrame completes in < 100ms [Spec §SC-005, tests/integration/test_engine_pipeline.py] — avg ~22ms after numpy optimisation
- [x] CHK046 — SC-006: Determinism test — identical DataFrame input produces identical `EntrySignal` output on consecutive calls [Spec §SC-006, tests/integration/test_engine_pipeline.py]
- [~] CHK047 — SC-007: `false_signals.json` entry appears within 1 second of discard — **GAP: no timing assertion planned** [Spec §SC-007, Gap]
- [x] CHK048 — SC-008: `pytest --cov=src/engine` reports ≥ 80% coverage for all 5 detection modules [Spec §SC-008, T023] — all 5 detectors ≥ 94%; total 97%
- [ ] CHK049 — SC-009: 2-year backtest — **OUT OF SCOPE** for this feature [Spec §SC-009]

---

## Infrastructure & Config

- [x] CHK050 — T001: `tests/unit/conftest.py` exists with `make_ohlcv(n, seed=42)` fixture factory [tasks.md §T001]
- [x] CHK051 — T004: `config.yaml` contains `smc_engine:` section with all required keys [data-model.md §Config Schema]
- [x] CHK052 — T003: `logs/false_signals.json` in `.gitignore` ✅; `logs/` dir exists ✅; scorer creates on first write ✅ [tasks.md §T003, T020]
- [x] CHK053 — T022: `src/engine/__init__.py` exports real `generate_signal`, `EntrySignal`, `Bias`, `Direction` ✅ [tasks.md §T022]

---

## Test Coverage

- [x] CHK054 — T008: `tests/unit/test_engine_swing.py` exists and covers confirmed vs unconfirmed pivots [tasks.md §T008]
- [x] CHK055 — T009: `tests/unit/test_engine_bos_choch.py` exists and covers wick rejection + close-through [tasks.md §T009]
- [x] CHK056 — T012: `tests/unit/test_engine_fvg.py` exists and covers bullish/bearish FVG + fill detection [tasks.md §T012]
- [x] CHK057 — T014: `tests/unit/test_engine_order_block.py` exists and covers ACTIVE→TESTED→INVALIDATED transitions [tasks.md §T014]
- [x] CHK058 — T016: `tests/unit/test_engine_liquidity_sweep.py` exists and covers sweep high/low + tolerance [tasks.md §T016]
- [x] CHK059 — T018: `tests/unit/test_engine_scorer.py` exists and covers full confluence + rejection + htf_bias filter [tasks.md §T018]
- [x] CHK060 — T019: `tests/integration/test_engine_pipeline.py` exists and covers end-to-end pipeline [tasks.md §T019]

---

## Ambiguities in Requirements

- [~] CHK061 — AMBIGUITY: `pip_tolerance` documented as "5 pips" in spec (FR-013) but as `float = 0.50` (dollar value) in contract and data-model. Are pips or dollars the canonical unit? [Ambiguity, Spec §FR-013, contracts/smc_engine.md]
- [~] CHK062 — AMBIGUITY: SC-003 success criterion (≥95% OB accuracy on hand-labelled dataset) has no task and is not explicitly deferred. Should this be tracked as a post-implementation validation item or removed from SC? [Gap, Spec §SC-003]
- [~] CHK063 — AMBIGUITY: SC-007 (false_signals.json within 1 second) has no timing test planned. Is this a hard requirement or a guideline? [Gap, Spec §SC-007]

---

## Summary

| Category | Total | Done ✅ | Partial ⚠️ | Missing ❌ |
|---|---|---|---|---|
| Models & Enums | 3 | 2 | 1 | 0 |
| BOS/CHoCH (FR-001–FR-004) | 5 | 5 | 0 | 0 |
| FVG (FR-005–FR-008) | 5 | 5 | 0 | 0 |
| Order Block (FR-009–FR-012) | 6 | 6 | 0 | 0 |
| Liquidity Sweep (FR-013–FR-016) | 5 | 5 | 0 | 0 |
| Scorer & Orchestrator (FR-017–FR-024) | 10 | 10 | 0 | 0 |
| Non-Functional Requirements | 3 | 3 | 0 | 0 |
| Success Criteria | 9 | 6 | 1 | 2 (deferred) |
| Infrastructure & Config | 4 | 4 | 0 | 0 |
| Test Coverage | 7 | 7 | 0 | 0 |
| Ambiguities | 3 | 0 | 3 | 0 |
| **Total** | **60** | **57 (95%)** | **4 (7%)** | **2 (3%)** |

> **Phase 1 complete (2026-05-15)**: CHK050 ✅, CHK051 ✅, CHK052 ⚠️ partial.
> **Phase 2 complete (2026-05-15)**: CHK001 ✅, CHK002 ✅, CHK003 ⚠️ partial, CHK053 ⚠️ partial.
> **Phase 3 complete (2026-05-15)**: CHK004–CHK011 ✅, CHK054–CHK055 ✅ — 21 tests pass.
> **Phase 4 complete (2026-05-15)**: CHK012–CHK016 ✅, CHK042 ✅, CHK056 ✅ — 16 new tests, 77 total pass.
> **Phase 5 complete (2026-05-15)**: CHK017–CHK022 ✅, CHK057 ✅ — 18 new tests, 95 total pass.
> **Phase 6 complete (2026-05-16)**: CHK023–CHK027 ✅, CHK038 ✅, CHK058 ✅ — 6 new tests, 101 total pass.
> **Phase 7 complete (2026-05-16)**: CHK028–CHK037 ✅, CHK039–CHK041 ✅, CHK059–CHK060 ✅ — 30 new tests (21 unit + 9 integration), 131 total pass. SC-001 ✅. NFR-002 ✅, NFR-003 ✅.
> **Phase 8 complete (2026-05-16)**: CHK044–CHK046 ✅, CHK048 ✅, CHK052–CHK053 ✅ — 3 new tests (T024 perf + SC-006, T025 smoke), 134 total pass. fvg.py + liquidity_sweep.py numpy-optimised (240ms→22ms). 97% engine coverage.
