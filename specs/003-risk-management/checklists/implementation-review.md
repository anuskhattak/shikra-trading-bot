# Implementation Review Checklist: Risk Management Module

**Purpose**: Track which spec requirements are implemented in code vs missing
**Created**: 2026-05-16
**Feature**: [spec.md](../spec.md)
**Code Under Review**: `src/risk/models.py`, `src/risk/lot_calculator.py`, `src/risk/drawdown_guard.py`, `src/risk/trade_limits.py`, `src/risk/recovery_mode.py`, `src/risk/risk_manager.py`

**Legend**: `[x]` = Done | `[ ]` = Missing | `[~]` = Partial / Gap

---

## Models — `src/risk/models.py`

- [x] CHK001 — T004: Enums defined — `RecoveryReason`, `BlockReason` [data-model.md §Enums]
- [x] CHK002 — T004: Dataclasses defined — `RiskCalculation`, `RiskState`, `TradeAllowedResult` with correct fields [data-model.md §Dataclasses]

---

## Lot Size & SL/TP — `src/risk/lot_calculator.py`

- [x] CHK003 — T006/FR-001: `calculate_lot_size()` implements formula: `(balance × risk_pct) / (sl_distance × pip_value_per_lot)` rounded to 2 dp; `sl_distance` in price units [Spec §FR-001]
- [x] CHK004 — T006/FR-002: Lot size clamped to minimum 0.01 [Spec §FR-002]
- [x] CHK005 — T006/FR-003: Lot size clamped to maximum `max_lot_size` [Spec §FR-003]
- [x] CHK006 — T006/FR-004: 5% hard cap applied before clamping (D-007) [Spec §FR-004]
- [x] CHK007 — T006/FR-005: `XAUUSD_PIP_VALUE = 10.0` defined as module constant [Spec §FR-005]
- [x] CHK008 — T006/FR-006: `calculate_sl_price()` returns SL below entry for LONG, above for SHORT [Spec §FR-006]
- [x] CHK009 — T006/FR-007: SL distance = `d1_atr × sl_atr_multiplier` [Spec §FR-007]
- [x] CHK010 — T006/FR-008: `calculate_tp_prices()` returns `(tp1, tp2)` tuple [Spec §FR-008]
- [x] CHK011 — T006/FR-009: TP1 = entry ± (sl_distance × tp1_rr_ratio) [Spec §FR-009]
- [x] CHK012 — T006/FR-010: TP2 = entry ± (sl_distance × tp2_rr_ratio) [Spec §FR-010]
- [x] CHK013 — T006/FR-011: LONG: SL < entry < TP1 < TP2; SHORT: TP2 < TP1 < entry < SL [Spec §FR-011]

---

## Drawdown Guard — `src/risk/drawdown_guard.py`

- [x] CHK014 — T008/FR-012: `check_drawdown()` returns `TradeAllowedResult` [Spec §FR-012]
- [x] CHK015 — T008/FR-013: Drawdown % formula correct [Spec §FR-013]
- [x] CHK016 — T008/FR-014: Trading blocked when drawdown ≥ max_pct; reason string includes actual% and limit% [Spec §FR-014]
- [x] CHK017 — T008/FR-015: `reset_daily_state()` updates equity and resets counters [Spec §FR-015]

---

## Trade Limits — `src/risk/trade_limits.py`

- [x] CHK018 — T010/FR-016: `is_trade_limit_allowed()` returns `TradeAllowedResult` [Spec §FR-016]
- [x] CHK019 — T010/FR-017: Daily trade limit enforced [Spec §FR-017]
- [x] CHK020 — T010/FR-018: Session trade limit enforced [Spec §FR-018]
- [x] CHK021 — T010/FR-019: Cooldown period enforced after SL hit [Spec §FR-019]
- [x] CHK022 — T010/FR-020: `record_trade_opened()` increments both counters [Spec §FR-020]
- [x] CHK023 — T010/FR-021: `record_sl_hit()` sets last_sl_time and increments consecutive_losses [Spec §FR-021]
- [x] CHK024 — T010/FR-022: `record_trade_won()` resets consecutive_losses to 0 [Spec §FR-022]

---

## Recovery Mode — `src/risk/recovery_mode.py`

- [x] CHK025 — T012/FR-023: Recovery activates when consecutive_losses ≥ max_consecutive_losses [Spec §FR-023]
- [x] CHK026 — T012/FR-024: Lot size multiplied by recovery_lot_multiplier in recovery [Spec §FR-024]
- [x] CHK027 — T012/FR-025: `is_signal_allowed_in_recovery()` blocks below min_confidence [Spec §FR-025]
- [x] CHK028 — T012/FR-026: Recovery exits when recovery_profit_pips ≥ target [Spec §FR-026]
- [x] CHK029 — T012/FR-027: `in_recovery_mode` flag and transitions logged to `logs/risk_events.json` [Spec §FR-027]
- [x] CHK029b — T012/FR-028: `update_recovery_profit(state, pips_gained_price_units)` correctly increments `recovery_profit_pips` and exits recovery at target [Spec §FR-028]

---

## Orchestrator — `src/risk/risk_manager.py`

- [x] CHK030 — T014/D-006: `evaluate_trade_risk()` is single entry point; calls all sub-modules in sequence [plan.md §D-006]
- [x] CHK031 — T014: Returns `zero_risk_calc` (lot=0.0) when trading blocked — never raises [contracts/risk_manager.md §Zero Risk Calculation]
- [x] CHK032 — T014: Returns `zero_risk_calc` when `entry_signal.direction == Direction.NONE`
- [x] CHK033 — T014/D-006: Returns `tuple[RiskCalculation, RiskState]` — state updated immutably [plan.md §D-001]

---

## Non-Functional Requirements

- [x] CHK034 — NFR-001: No `MetaTrader5` or `mt5` import in any `src/risk/` module [Spec §NFR-001]
- [x] CHK035 — NFR-002: All calculation functions are pure (same inputs → same outputs) [Spec §NFR-002]
- [x] CHK036 — NFR-003: `RiskState` is a dataclass; no global state used [Spec §NFR-003]
- [x] CHK037 — NFR-004: All public functions have type hints and one-line docstrings [Spec §NFR-004]
- [x] CHK038 — NFR-005: `logs/risk_events.json` written for drawdown block, recovery enter/exit, SL hit [Spec §NFR-005]
- [x] CHK038b — NFR-006: `evaluate_trade_risk()` appends DEBUG entry to `logs/risk_events.json` on `allowed=True`; write failure is silent [Spec §NFR-006]

---

## Success Criteria

- [x] CHK039 — SC-001: Unit test: balance=10000, risk=1%, SL=20 pips → lot matches formula [Spec §SC-001]
- [x] CHK040 — SC-002: Unit test: drawdown=6% on 5% limit → allowed=False [Spec §SC-002]
- [x] CHK041 — SC-003: Unit test: LONG entry=2350, D1_ATR=20, mult=1.5 → SL=2320, TP1=2395, TP2=2440 [Spec §SC-003]
- [x] CHK042 — SC-004: Unit test: consecutive_losses=3 → recovery active, lot halved [Spec §SC-004]
- [x] CHK043 — SC-005: Unit test: confidence=0.75, min=0.80 → rejected in recovery [Spec §SC-005]
- [x] CHK044 — SC-006: Unit test: lot ≥ 0.01 and ≤ max_lot regardless of extreme inputs [Spec §SC-006]
- [x] CHK045 — SC-007: Unit test: SHORT → SL above entry, TP1/TP2 below entry [Spec §SC-007]
- [x] CHK046 — SC-008: `pytest --cov=src/risk` reports ≥ 80% coverage [Spec §SC-008] — 94% achieved
- [x] CHK047 — SC-009: `grep -r "MetaTrader5\|import mt5" src/risk/` returns zero results [Spec §SC-009]

---

## Infrastructure & Config

- [x] CHK048 — T001/T015: `src/risk/__init__.py` exists and exports complete (T015 done)
- [x] CHK049 — T002: `config.yaml` contains `risk:` section with all required keys
- [x] CHK050 — T003: `logs/risk_events.json` in `.gitignore`

---

## Test Coverage

- [x] CHK051 — T005/T005b: `tests/unit/test_risk_lot_calculator.py` exists with 13 tests
- [x] CHK052 — T007: `tests/unit/test_risk_drawdown_guard.py` exists with 7 tests
- [x] CHK053 — T009: `tests/unit/test_risk_trade_limits.py` exists with 10 tests
- [x] CHK054 — T011: `tests/unit/test_risk_recovery_mode.py` exists with 7 tests
- [x] CHK055 — T013: `tests/integration/test_risk_pipeline.py` exists with 6 tests

---

## Summary

| Category | Total | Done ✅ | Partial ⚠️ | Missing ❌ |
|---|---|---|---|---|
| Models | 2 | 2 | 0 | 0 |
| Lot/SL/TP | 11 | 11 | 0 | 0 |
| Drawdown Guard | 4 | 4 | 0 | 0 |
| Trade Limits | 7 | 7 | 0 | 0 |
| Recovery Mode | 6 | 6 | 0 | 0 |
| Orchestrator | 4 | 4 | 0 | 0 |
| Non-Functional | 6 | 6 | 0 | 0 |
| Success Criteria | 9 | 9 | 0 | 0 |
| Infrastructure | 3 | 3 | 0 | 0 |
| Test Coverage | 5 | 5 | 0 | 0 |
| **Total** | **57** | **57 (100%)** | **0** | **0** |

> ALL PHASES COMPLETE 2026-05-16: T001–T018 done. 43 tests pass. Coverage 94%. mypy clean. ruff clean. No MT5 imports.
