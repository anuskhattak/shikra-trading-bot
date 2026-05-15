# Specification Quality Checklist: SMC Signal Detection Engine

**Purpose**: Validate specification completeness and quality before proceeding to implementation
**Created**: 2026-05-14
**Feature**: [spec.md](../spec.md)

---

## Content Quality

- [x] No implementation details (languages, frameworks, APIs) leak into spec
- [x] Focused on signal detection rules and business outcomes
- [x] All mandatory sections completed (Overview, Requirements, User Stories, Success Criteria, NFRs, Edge Cases, Assumptions)
- [x] Out-of-scope clearly bounded (M5 refinement, ML filter, LSTM bias, S&D zones excluded)

---

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain — 5 clarifications resolved on 2026-05-12
- [x] All 5 SMC concepts have dedicated functional requirements (BOS/CHoCH: FR-001–FR-004, FVG: FR-005–FR-008, OB: FR-009–FR-012, LS: FR-013–FR-016, Scorer: FR-017–FR-024)
- [x] Each user story has defined acceptance scenarios (US1: 3, US2: 3, US3: 3, US4: 3, US5: 4)
- [x] Candle-close rule stated explicitly for BOS (FR-004), FVG fill (FR-007), and OB invalidation (FR-011)
- [x] EntrySignal output contract fully defined: direction, confidence, entry_zone, reason, components, timestamp [Spec §FR-017]
- [x] Confidence scoring formula documented with default weights that sum to 1.0 [Spec §Assumptions 4]
- [x] Minimum candle requirement defined (50 bars) with fallback behaviour (returns NONE) [Spec §Assumptions 2]
- [x] Edge cases section covers 6 scenarios: insufficient bars, BOS/CHoCH conflict, stacked FVGs, OB+FVG overlap, FVG-only entry, news spike

---

## Requirement Clarity

- [x] BOS definition unambiguous: "candle closes beyond most recent swing high/low" [Spec §FR-002]
- [x] CHoCH definition unambiguous: "closes beyond swing low in established bullish trend" [Spec §FR-003]
- [x] "Established trend" defined explicitly as direction of most recent confirmed BOS [Spec §Clarifications Q3, plan.md D-006]
- [x] FVG boundaries specified: top = candle[N].low, bottom = candle[N-2].high for bullish [Spec §FR-005]
- [x] OB boundaries use candle body only (open/close), not wicks — explicitly stated [Spec §FR-012]
- [x] TESTED vs INVALIDATED distinction clear: wick→TESTED, close-through→INVALIDATED [data-model.md §OBStatus]
- [~] "Equal highs" definition uses pip tolerance ($0.50) but spec says "5 pips" — unit labelling inconsistent between spec and contract [Ambiguity, Spec §FR-013, contracts/smc_engine.md]
- [x] `htf_bias` is caller-provided enum — engine does not derive it — explicitly documented [Spec §FR-021, Clarifications Q2]

---

## Acceptance Criteria Quality

- [x] SC-001 measurable: "zero false positives on wick-only moves" — binary pass/fail [Spec §SC-001]
- [x] SC-002 measurable: "precision to 2 decimal places" [Spec §SC-002]
- [x] SC-005 measurable: "< 100ms for 200 H1 candles" [Spec §SC-005]
- [x] SC-006 measurable: "identical input always produces identical score" — determinism [Spec §SC-006]
- [x] SC-008 measurable: "≥ 80% unit test coverage" [Spec §SC-008]
- [~] SC-003: "≥ 95% of cases when tested against hand-labelled dataset of 200 setups" — no task or plan to create this dataset; deferred status not declared [Gap, Spec §SC-003]
- [~] SC-007: "false_signals.json within 1 second" — timing assertion not covered by any task; no test planned [Gap, Spec §SC-007]
- [x] SC-009 scope noted: requires 2+ years backtest data — explicitly out of scope for this feature [Spec §SC-009]

---

## Scenario Coverage

- [x] Happy path defined: BOS + FVG + OB + LS → full confidence signal [Spec §US5, SC-001 to SC-009]
- [x] Minimum viable path defined: BOS + FVG only → confidence 0.70 (above threshold) [data-model.md §Confidence Scoring]
- [x] Rejection path defined: BOS only → confidence 0.40 → discarded, logged [Spec §US5 Acceptance Scenario 2]
- [x] No-signal path defined: ranging market → SignalType.NONE [Spec §US1 Acceptance Scenario 3]
- [x] Insufficient data path defined: < 50 candles → NONE signal, warning logged [Spec §Assumptions 2, Edge Cases]
- [x] Bias filter path defined: misaligned signal rejected when htf_bias set [Spec §FR-021]
- [x] Conflict resolution defined: most recent structural event takes precedence [Spec §Edge Cases]

---

## Non-Functional Requirements

- [x] Performance requirement quantified: < 100ms / 200 candles [Spec §SC-005, NFR section]
- [x] Statelessness requirement defined: full recompute on every call [Spec §NFR-002]
- [x] Broker independence requirement defined: no MT5 import in engine [Spec §NFR-003]
- [~] NFR-001 (inline SMC comments) defined in spec but **not covered by any task** — gap identified and remediated in tasks.md (2026-05-14) [Spec §NFR-001, tasks.md T010/T011/T013/T015/T017]
- [x] Auditability requirement defined: false_signals.json for every discard [Spec §FR-023]
- [x] Determinism requirement defined: identical input → identical output [Spec §SC-006]

---

## Dependencies & Assumptions

- [x] Dependency on 001-mt5-broker documented: `MarketData.get_ohlcv()` provides DataFrame [Spec §Depends On, Assumptions 1]
- [x] DataFrame schema assumed: [time, open, high, low, close, tick_volume] with types [contracts/smc_engine.md §DataFrame Input Contract]
- [x] Row ordering assumed: ascending by time (oldest first) [contracts/smc_engine.md]
- [x] NaN assumption documented: no NaN allowed in OHLC columns [contracts/smc_engine.md]
- [x] XAUUSD pip value assumption documented: 1 pip = $0.10 ($0.50 = 5 pips) [Spec §Assumptions 3]
- [x] All configurable parameters documented with defaults in config schema [data-model.md §Config Schema]

---

## Notes

- 7 items PASS with full confidence ✅
- 4 items PARTIAL `[~]` — non-blocking but noted for awareness:
  1. **A1**: pip_tolerance unit terminology inconsistency (spec says "pips", contract says "float dollars")
  2. **SC-003**: Hand-labelled validation dataset — deferred, not explicitly marked out-of-scope
  3. **SC-007**: false_signals.json timing test — no task covers this assertion
  4. **NFR-001**: Gap resolved in tasks.md via T010/T011/T013/T015/T017 mandate
- Spec is **ready for `/sp.implement`** — no blocking issues
