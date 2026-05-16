# Implementation Plan: Risk Management Module

**Feature**: 003-risk-management
**Created**: 2026-05-16
**Status**: Ready

---

## Objective

Build the `src/risk/` module — a broker-agnostic, pure-function risk calculation layer that sits between the SMC engine output (`EntrySignal`) and the execution engine (spec004). All logic testable without MT5 connection.

---

## Architecture

```
EntrySignal (from spec002)
        │
        ▼
┌──────────────────────────────────┐
│       src/risk/                  │
│                                  │
│  lot_calculator.py               │
│    calculate_lot_size()          │
│    calculate_sl_price()          │
│    calculate_tp_prices()         │
│                                  │
│  drawdown_guard.py               │
│    check_drawdown()              │
│    reset_daily_state()           │
│                                  │
│  trade_limits.py                 │
│    is_trade_limit_allowed()      │
│    record_trade_opened()         │
│    record_sl_hit()               │
│    record_trade_won()            │
│                                  │
│  recovery_mode.py                │
│    check_recovery_status()       │
│    is_signal_allowed_in_recovery()│
│    apply_recovery_lot()          │
│                                  │
│  risk_manager.py   ← main entry  │
│    evaluate_trade_risk()         │
│                                  │
│  models.py                       │
│    RiskCalculation, RiskState    │
│    TradeAllowedResult            │
└──────────────────────────────────┘
        │
        ▼
  RiskCalculation (lot, SL, TP1, TP2)
        │
        ▼
  spec004 — Execution Engine
```

---

## Key Design Decisions

### D-001: Pure Functions, No Global State
All calculation functions accept and return explicit values. `RiskState` is a dataclass owned by the caller (main loop), not a singleton. All functions that modify state return a **new** `RiskState` instance; the input state is never mutated in-place (functional update pattern, per NFR-003). This allows unit testing without mocking.

### D-002: ATR Passed as Parameter
The risk module does not fetch ATR from MT5 or from disk. The caller passes `d1_atr` as a float. This keeps the module broker-agnostic and testable.

### D-003: Entry Price from EntrySignal
`entry_price` for lot size and SL/TP calculation is taken as `(entry_zone_top + entry_zone_bottom) / 2` (midpoint of zone). Spec004 (Execution Engine) will handle the exact limit order placement.

### D-004: XAUUSD Pip Value is Constant
For XAUUSD, pip_value_per_lot = $10.00. This is a constant defined in `lot_calculator.py`, not config, because it is a broker/symbol specification, not a user preference. A comment explains this.

### D-005: Recovery Mode is State-Driven, Not Time-Driven
Recovery exits when `recovery_profit_pips >= target`, not after a fixed number of trades. This is more adaptive. The caller updates `recovery_profit_pips` after each closed trade.

### D-006: `evaluate_trade_risk()` is the Single Entry Point
The main orchestrator function in `risk_manager.py` calls all sub-modules in sequence and returns a single `RiskCalculation`. This mirrors `generate_signal()` in spec002.

### D-007: 5% Hard Cap Applied Before Lot Clamping
The order of operations: calculate raw lot → apply 5% hard cap → clamp to [min_lot, max_lot]. This ensures the hard cap is never bypassed by the min lot floor.

---

## Module Breakdown

### `src/risk/models.py`
- Enums: `RecoveryReason`, `BlockReason`
- Dataclasses: `RiskCalculation`, `RiskState`, `TradeAllowedResult`

### `src/risk/lot_calculator.py`
- `calculate_lot_size(balance, risk_percent, sl_distance, pip_value_per_lot, max_lot, min_lot) -> float`
- `calculate_sl_price(entry, direction, d1_atr, sl_atr_multiplier) -> float`
- `_calculate_sl_distance(d1_atr, sl_atr_multiplier) -> float`  ← private helper; not public API (FR-007)
- `calculate_tp_prices(entry, sl_price, direction, tp1_rr, tp2_rr) -> tuple[float, float]`

### `src/risk/drawdown_guard.py`
- `check_drawdown(day_start_equity, current_equity, max_pct) -> TradeAllowedResult`
- `reset_daily_state(state, current_equity) -> RiskState`
- `get_drawdown_pct(day_start_equity, current_equity) -> float`

### `src/risk/trade_limits.py`
- `is_trade_limit_allowed(state, config, current_time, session) -> TradeAllowedResult`
- `record_trade_opened(state, session) -> RiskState`
- `record_sl_hit(state, current_time) -> RiskState`
- `record_trade_won(state) -> RiskState`

### `src/risk/recovery_mode.py`
- `check_recovery_status(state, config) -> RiskState`
- `is_signal_allowed_in_recovery(confidence, recovery_min_confidence) -> bool`
- `apply_recovery_lot(lot_size, recovery_lot_multiplier) -> float`
- `update_recovery_profit(state, pips_gained_price_units) -> RiskState`  ← called by spec004 (Execution Engine) after each closed trade (FR-028)

### `src/risk/risk_manager.py`
- `evaluate_trade_risk(entry_signal, balance, current_equity, d1_atr, state, config) -> tuple[RiskCalculation, RiskState]`
- Logs successful evaluations (`allowed=True`) to `logs/risk_events.json` at DEBUG level (NFR-006); silent fail on write error

### `src/risk/__init__.py`
- Exports: `evaluate_trade_risk`, `RiskCalculation`, `RiskState`, `TradeAllowedResult`, `reset_daily_state`, `record_trade_opened`, `record_sl_hit`, `record_trade_won`

---

## Test Strategy

### Unit Tests (one file per module)
- `tests/unit/test_risk_lot_calculator.py` — FR-001–FR-011
- `tests/unit/test_risk_drawdown_guard.py` — FR-012–FR-015
- `tests/unit/test_risk_trade_limits.py` — FR-016–FR-022
- `tests/unit/test_risk_recovery_mode.py` — FR-023–FR-027

### Integration Tests
- `tests/integration/test_risk_pipeline.py` — end-to-end: EntrySignal → evaluate_trade_risk → RiskCalculation

### Coverage Target
≥ 80% for all `src/risk/` modules (SC-008)

---

## Phased Delivery

```
Phase 1: models.py — enums + dataclasses (blocking)
Phase 2: lot_calculator.py + tests (P1 — core)
Phase 3: drawdown_guard.py + tests (P1 — safety)
Phase 4: trade_limits.py + tests (P2 — limits)
Phase 5: recovery_mode.py + tests (P3 — recovery)
Phase 6: risk_manager.py + integration tests (orchestrator)
Phase 7: __init__.py, config.yaml update, coverage check
```
