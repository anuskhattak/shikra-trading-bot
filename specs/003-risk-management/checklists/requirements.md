# Specification Quality Checklist: Risk Management Module

**Purpose**: Validate specification completeness and quality before proceeding to implementation
**Created**: 2026-05-16
**Feature**: [spec.md](../spec.md)

---

## Content Quality

- [x] No implementation details (languages, frameworks, APIs) leak into spec
- [x] Focused on risk rules and capital-preservation outcomes
- [x] All mandatory sections completed (Overview, User Stories, Functional Requirements, NFRs, Success Criteria, Out of Scope)
- [x] Out-of-scope clearly bounded (trailing stop, basket recovery, ATR fetching, position closing, session detection excluded)

---

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] All 5 risk sub-modules have dedicated functional requirements (Lot: FR-001–FR-005, SL/TP: FR-006–FR-011, Drawdown: FR-012–FR-015, Trade Limits: FR-016–FR-022, Recovery: FR-023–FR-028)
- [x] Each user story has defined acceptance scenarios (US1: 4, US2: 4, US3: 3, US4: 4, US5: 4)
- [x] `lot_size` invariants fully defined: ≥ 0.01, ≤ max_lot_size, risk_amount ≤ 5% of balance [Spec §FR-002–FR-004]
- [x] `RiskCalculation` output contract fully defined: lot_size, sl_price, tp1_price, tp2_price, sl_distance, risk_amount_usd, in_recovery, reason [data-model.md §RiskCalculation]
- [x] SL/TP price ordering invariants defined for both LONG and SHORT directions [Spec §FR-011]
- [x] `RiskState` fields all defined with types and initial values [data-model.md §RiskState]
- [x] Zero risk calculation format defined for blocked trades [contracts/risk_manager.md §Zero Risk Calculation]
- [x] All configurable parameters have defaults documented in config schema [data-model.md §Config Schema]

---

## Requirement Clarity

- [x] Lot size formula unambiguous: `(balance × risk_pct) / (sl_distance × pip_value_per_lot)` where `sl_distance` is in price units [data-model.md §XAUUSD Pip Value Reference]
- [x] XAUUSD pip value documented: $10.00 per standard lot — derived from contract specs, not config [data-model.md §XAUUSD Pip Value Reference, research.md]
- [x] 5% hard cap application order defined: cap first, then clamp [plan.md §D-007]
- [x] Drawdown % formula unambiguous: `(day_start_equity - current_equity) / day_start_equity × 100` [Spec §FR-013]
- [x] "Recovery exits" condition defined: `recovery_profit_pips >= target` (not # of trades) [Spec §FR-026, research.md]
- [x] ATR is caller-provided — risk module does not fetch ATR from MT5 [plan.md §D-002, data-model.md §Key Entities]
- [x] Entry price source documented: midpoint of `(entry_zone_top + entry_zone_bottom) / 2` [plan.md §D-003]
- [x] "Cooldown" trigger defined: `current_time - last_sl_time < cooldown_after_sl_hours` [Spec §FR-019]

---

## Acceptance Criteria Quality

- [x] SC-001 measurable: exact lot formula check with specific input values [Spec §SC-001]
- [x] SC-002 measurable: binary pass/fail on drawdown block at 6% > 5% limit [Spec §SC-002]
- [x] SC-003 measurable: specific prices — SL=2320.00, TP1=2395.00, TP2=2440.00 [Spec §SC-003]
- [x] SC-004 measurable: lot halved when consecutive_losses=3 [Spec §SC-004]
- [x] SC-005 measurable: confidence=0.75 rejected at min=0.80 — binary [Spec §SC-005]
- [x] SC-006 measurable: edge inputs (extreme balance, zero SL) → lot still in [0.01, max] [Spec §SC-006]
- [x] SC-007 measurable: SHORT direction produces inverted SL/TP ordering [Spec §SC-007]
- [x] SC-008 measurable: ≥ 80% pytest coverage [Spec §SC-008]
- [x] SC-009 measurable: grep returns zero lines [Spec §SC-009]

---

## Scenario Coverage

- [x] Happy path defined: valid EntrySignal + healthy equity + no limits → RiskCalculation with non-zero lot [contracts/risk_manager.md]
- [x] Blocked path defined: lot_size=0.0 when any guard fires; caller checks `lot_size == 0.0` [contracts/risk_manager.md §Zero Risk Calculation]
- [x] NONE signal path defined: EntrySignal.direction=NONE → zero_risk_calc [contracts/risk_manager.md]
- [x] Recovery path defined: lot reduced, low-confidence signals rejected [Spec §US5]
- [x] Drawdown breach path defined: trading blocked, reason returned [Spec §US3]
- [x] Daily limit path defined: trades_today >= max → blocked [Spec §US4]
- [x] Session limit path defined: session_trades >= max → blocked [Spec §US4]
- [x] Cooldown path defined: SL hit < 2h ago → blocked [Spec §US4]
- [x] SHORT direction path defined: SL above entry, TP below entry [Spec §US2, SC-007]

---

## Non-Functional Requirements

- [x] Broker independence defined: no MT5 import in any `src/risk/` module [Spec §NFR-001]
- [x] Pure function requirement defined: same inputs → same outputs [Spec §NFR-002]
- [x] Stateless design defined: `RiskState` passed explicitly, no global state [Spec §NFR-003]
- [x] Type hints requirement defined for all public functions [Spec §NFR-004]
- [x] Audit log requirement defined: risk_events.json for drawdown block, recovery, SL hit (blocking events) [Spec §NFR-005]; successful evaluations logged at DEBUG level [Spec §NFR-006]

---

## Dependencies & Assumptions

- [x] Dependency on 001-mt5-broker documented: account balance and equity from `mt5.account_info()` [spec.md §Depends On]
- [x] Dependency on 002-smc-engine documented: `EntrySignal` as input type [spec.md §Depends On]
- [x] ATR fetch responsibility documented: caller provides D1 ATR, not this module [plan.md §D-002]
- [x] `RiskState` ownership documented: caller (main loop) owns and passes state; module returns updated copy [plan.md §D-001]
- [x] XAUUSD-specific pip value documented with derivation [data-model.md §XAUUSD Pip Value Reference, research.md]
- [x] `config` parameter documented: `risk:` section from config.yaml; None uses defaults [contracts/risk_manager.md]

---

## Notes

- All items PASS ✅ — no blocking gaps or ambiguities
- Spec is **ready for implementation** — proceed with `Phase 1 implement karo`
- One design note: entry price uses zone midpoint (D-003) — spec004 Execution Engine will override with actual limit order price; this is acceptable for lot-size calculation purposes
