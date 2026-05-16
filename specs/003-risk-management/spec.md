# Feature Specification: Risk Management Module

**Feature Branch**: `003-risk-management`
**Created**: 2026-05-16
**Status**: Draft
**Asset**: XAUUSD only
**Depends On**: 001-mt5-broker (account info, position data), 002-smc-engine (EntrySignal)

---

## Clarifications

### Session 2026-05-16

- Q: What timezone does `current_time` use for cooldown calculation and daily reset? → A: UTC throughout — all internal timestamps in UTC; daily reset at UTC 00:00.
- Q: What happens when `d1_atr <= 0` is passed to `calculate_sl_price()`? → A: Raise `ValueError` — zero/negative ATR is invalid input; caller is responsible for providing valid data.
- Q: What is `day_start_equity` when bot starts mid-day? → A: Use current equity at startup — documented limitation: mid-day restart resets drawdown history for that day; caller does not need to provide historical equity.
- Q: `sl_distance_pips` variable name vs price-unit value — what is the canonical name? → A: Rename to `sl_distance` (price units) — `sl_distance_pips` is misleading; XAUUSD ATR is in price units not pips.
- Q: What happens when `logs/risk_events.json` write fails (disk full / permissions)? → A: Silent fail — log error to stderr/loguru, trade proceeds normally; logging failure must not block capital operations.

---

## Overview

The Risk Management Module is the capital-preservation layer of the Shikra system. It takes a raw `EntrySignal` from the SMC engine and converts it into a trade-ready `RiskCalculation` — with lot size, SL price, TP1/TP2 prices — while enforcing all safety constraints: daily drawdown limits, per-day/per-session trade caps, cooldown periods, and recovery mode after consecutive losses.

All core logic is **pure functions with no MetaTrader5 import**. The module is designed to be fully testable without a live broker connection.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Lot Size Calculated from Risk Parameters (Priority: P1)

The system determines the correct lot size for each trade so that the maximum loss (if stop loss is hit) never exceeds the configured risk percentage of account balance.

**Why this priority**: Incorrect lot sizing is the #1 cause of account blowup. This must be correct before any other feature.

**Independent Test**: Given balance=10,000, risk_percent=1.0, SL=20 pips → calculated lot size should equal the formula result, clamped to [0.01, max_lot_size].

**Acceptance Scenarios**:

1. **Given** account balance = $10,000 and risk_percent = 1.0%, **When** SL distance = 20 pips, **Then** lot size is calculated as `(10000 × 0.01) / (20 × pip_value_per_lot)` rounded to 2 decimal places.
2. **Given** a calculated lot size below 0.01, **When** clamping is applied, **Then** returned lot size is exactly 0.01 (minimum MT5 lot).
3. **Given** a calculated lot size above `max_lot_size`, **When** clamping is applied, **Then** returned lot size equals `max_lot_size`.
4. **Given** risk amount would exceed 5% of balance, **When** hard cap is checked, **Then** lot size is reduced so the maximum possible loss ≤ 5% of balance.

---

### User Story 2 — SL and TP Prices Calculated from ATR (Priority: P1)

Stop loss and take profit levels are set dynamically using the Daily ATR, so they adapt to current market volatility instead of using fixed pip distances.

**Why this priority**: Fixed SL/TP are ineffective in volatile markets. ATR-based levels keep the system adaptive.

**Independent Test**: Given entry price = 2350.00, direction = LONG, D1_ATR = 20.0, sl_atr_multiplier = 1.5 → SL = 2320.00, TP1 = 2395.00 (1.5 RR), TP2 = 2440.00 (3.0 RR).

**Acceptance Scenarios**:

1. **Given** a LONG entry at 2350.00 and D1_ATR = 20.0 with sl_atr_multiplier = 1.5, **When** SL is calculated, **Then** SL = 2350.00 − (20.0 × 1.5) = 2320.00.
2. **Given** SL distance calculated above, **When** TP1 is calculated, **Then** TP1 = entry + (SL_distance × TP1_RR_RATIO) for LONG.
3. **Given** SL distance calculated above, **When** TP2 is calculated, **Then** TP2 = entry + (SL_distance × TP2_RR_RATIO) for LONG.
4. **Given** a SHORT entry, **When** SL/TP are calculated, **Then** SL is above entry and both TPs are below entry.

---

### User Story 3 — Daily Drawdown Guard Blocks Trading (Priority: P1)

If the account equity drops by more than `max_daily_drawdown` percent from the start-of-day equity, all trading is blocked for the rest of the calendar day.

**Why this priority**: This is the primary safety net against catastrophic single-day losses.

**Independent Test**: Given day_start_equity = 10,000 and current_equity = 9,400, with max_daily_drawdown = 5.0% → drawdown = 6% → trading blocked. Given current_equity = 9,600 → drawdown = 4% → trading allowed.

**Acceptance Scenarios**:

1. **Given** day_start_equity = 10,000 and current_equity = 9,400, **When** drawdown check runs, **Then** `check_drawdown()` returns `TradeAllowedResult(allowed=False, reason="Daily drawdown limit reached (6.0% >= 5.0%)")`.
2. **Given** day_start_equity = 10,000 and current_equity = 9,600, **When** drawdown check runs, **Then** `check_drawdown()` returns `TradeAllowedResult(allowed=True)`.
3. **Given** a new calendar day begins (UTC 00:00), **When** `reset_daily_state()` is called, **Then** `day_start_equity` updates to current equity and `trades_today` counter resets to 0.

---

### User Story 4 — Trade Limits Enforced (Priority: P2)

The system enforces per-day and per-session trade caps, and imposes a cooldown period after a stop loss is hit.

**Why this priority**: Over-trading is a common cause of loss. Hard limits prevent revenge trading.

**Independent Test**: Given trades_today = 5, max_trades_per_day = 5 → next trade blocked. Given last_sl_time = 30 minutes ago, cooldown = 2 hours → trade blocked. Given last_sl_time = 3 hours ago → trade allowed.

**Acceptance Scenarios**:

1. **Given** `trades_today >= max_trades_per_day`, **When** trade is requested, **Then** `is_trade_limit_allowed()` returns `TradeAllowedResult(allowed=False, reason="Daily trade limit reached")`.
2. **Given** `session_trades >= max_trades_per_session` for current session, **When** trade is requested, **Then** `is_trade_limit_allowed()` returns `TradeAllowedResult(allowed=False, reason="Session trade limit reached")`.
3. **Given** a stop loss was hit less than `cooldown_after_sl` hours ago, **When** trade is requested, **Then** `is_trade_limit_allowed()` returns `TradeAllowedResult(allowed=False, reason="Cooldown active after SL")`.
4. **Given** `consecutive_losses >= max_consecutive_losses`, **When** a trade is requested, **Then** `is_trade_limit_allowed()` returns `allowed=True` for the limit check — recovery mode **activation** is the orchestrator's responsibility (`evaluate_trade_risk()` calls `check_recovery_status()` after the trade limit check). See US5 / FR-023.

---

### User Story 5 — Recovery Mode Reduces Risk After Losses (Priority: P3)

After `max_consecutive_losses` consecutive stop loss hits, the system enters recovery mode: lot size is reduced and only highest-confidence signals are accepted.

**Why this priority**: Drawdown sequences are most dangerous when the system continues full-size trading. Recovery mode is a circuit breaker.

**Independent Test**: Given consecutive_losses = 3, max_consecutive_losses = 3, recovery_lot_multiplier = 0.5 → next lot size = normal_lot × 0.5. Given signal confidence = 0.75, recovery_min_confidence = 0.80 → signal rejected in recovery mode.

**Acceptance Scenarios**:

1. **Given** recovery mode is active and normal lot = 0.10, **When** lot size is calculated, **Then** returned lot = 0.10 × 0.5 = 0.05.
2. **Given** recovery mode is active and signal confidence = 0.75 < recovery_min_confidence = 0.80, **When** signal is checked, **Then** `is_signal_allowed_in_recovery()` returns False.
3. **Given** recovery mode is active and total recovery profit >= `recovery_profit_target` pips, **When** recovery check runs, **Then** recovery mode exits and normal parameters resume.
4. **Given** a winning trade (no SL hit), **When** trade closes at profit, **Then** `consecutive_losses` counter resets to 0.

---

## Functional Requirements

### Lot Size Calculation

| ID | Requirement |
|----|-------------|
| FR-001 | `calculate_lot_size(balance, risk_percent, sl_distance, pip_value_per_lot)` returns float rounded to 2 decimal places; `sl_distance` is in price units (same unit as D1_ATR, e.g. 30.0 = $30 move) |
| FR-002 | Returned lot size is always ≥ 0.01 (MT5 minimum) |
| FR-003 | Returned lot size is always ≤ `max_lot_size` (configurable, default 5.0) |
| FR-004 | If `risk_amount > balance × 0.05`, lot size is reduced so loss ≤ 5% of balance (hard cap) |
| FR-005 | `pip_value_per_lot` for XAUUSD = $10.00 per pip per standard lot (1 lot = 100 oz) |

### SL / TP Calculation

| ID | Requirement |
|----|-------------|
| FR-006 | `calculate_sl_price(entry, direction, d1_atr, sl_atr_multiplier)` returns SL below entry for LONG, above for SHORT |
| FR-006a | `calculate_sl_price()` raises `ValueError` if `d1_atr <= 0` or `entry <= 0` — invalid inputs must not silently produce a wrong SL |
| FR-007 | `sl_distance = d1_atr × sl_atr_multiplier` — result is in price units (e.g. 30.0 = $30 move); canonical name is `sl_distance` not `sl_distance_pips`; private helper `_calculate_sl_distance(d1_atr, sl_atr_multiplier) -> float` computes this value inside `lot_calculator.py` (not public API) |
| FR-008 | `calculate_tp_prices(entry, sl_price, tp1_rr, tp2_rr)` returns (tp1, tp2) tuple |
| FR-009 | TP1 = entry ± (sl_distance × tp1_rr_ratio); default tp1_rr_ratio = 1.5 |
| FR-010 | TP2 = entry ± (sl_distance × tp2_rr_ratio); default tp2_rr_ratio = 3.0 |
| FR-011 | For LONG: SL < entry < TP1 < TP2; For SHORT: TP2 < TP1 < entry < SL |

### Drawdown Guard

| ID | Requirement |
|----|-------------|
| FR-012 | `check_drawdown(day_start_equity, current_equity, max_pct)` returns `TradeAllowedResult` |
| FR-013 | Drawdown % = `(day_start_equity - current_equity) / day_start_equity × 100` |
| FR-014 | When drawdown ≥ max_daily_drawdown, trading is blocked (allowed=False) with reason string |
| FR-015 | `reset_daily_state()` updates day_start_equity and resets trades_today and session_trades counters at UTC 00:00; session trade counters do NOT reset at intra-day session boundaries |
| FR-015a | `RiskState` is initialized with `day_start_equity = current_equity` at bot startup — known limitation: mid-day restart clears that day's drawdown history; this is acceptable and must be documented in code |

### Trade Limits

| ID | Requirement |
|----|-------------|
| FR-016 | `is_trade_limit_allowed(state, config, current_time, session)` returns `TradeAllowedResult`; `session: str` is the current trading session name (e.g. `"LONDON"`, `"NEW_YORK"`) — required by FR-018 |
| FR-017 | Trading blocked when `state.trades_today >= config.max_trades_per_day` |
| FR-018 | Trading blocked when `state.session_trades[session] >= config.max_trades_per_session` |
| FR-019 | Trading blocked when `current_time - state.last_sl_time < cooldown_after_sl`; `current_time` is always UTC (`datetime.utcnow()`) |
| FR-020 | `record_trade_opened(state, session)` increments `trades_today` and `session_trades[session]` |
| FR-021 | `record_sl_hit(state, current_time)` sets `last_sl_time = current_time` (UTC) and increments `consecutive_losses` |
| FR-022 | `record_trade_won(state)` resets `consecutive_losses = 0` |

### Recovery Mode

| ID | Requirement |
|----|-------------|
| FR-023 | Recovery mode activates when `state.consecutive_losses >= config.max_consecutive_losses` |
| FR-024 | In recovery mode, lot size multiplied by `recovery_lot_multiplier` (default 0.5) before clamping |
| FR-025 | In recovery mode, `is_signal_allowed_in_recovery(confidence, min_confidence)` blocks signals below `recovery_min_confidence` |
| FR-026 | Recovery mode exits when `state.recovery_profit_pips >= config.recovery_profit_target` |
| FR-027 | `state.in_recovery_mode` is a bool flag; changes logged to `logs/risk_events.json` |
| FR-028 | `update_recovery_profit(state, pips_gained_price_units)` is called by the Execution Engine (spec004) after each closed trade; increments `state.recovery_profit_pips` by `pips_gained_price_units`; triggers `check_recovery_status()` to re-evaluate exit condition (FR-026) |

---

## Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-001 | No `import MetaTrader5` or `import mt5` in any `src/risk/` module — all logic is broker-agnostic |
| NFR-002 | All calculation functions are pure: same inputs → same outputs, no side effects |
| NFR-003 | `RiskState` is a dataclass; all functions that modify state return a **new** `RiskState` instance — the input state is never mutated in-place (functional update pattern). No global state. |
| NFR-004 | All functions have type hints and one-line docstrings explaining the rule |
| NFR-005 | `logs/risk_events.json` entries written for: drawdown block, recovery mode enter/exit, SL hit (blocking events) — write failures are silent (log to stderr via loguru); a log failure must never block a trade calculation. See NFR-006 for successful evaluation logging. |
| NFR-006 | Every successful call to `evaluate_trade_risk()` that returns `allowed=True` appends a DEBUG-level entry to `logs/risk_events.json` containing: `timestamp` (UTC ISO), `lot_size`, `sl_price`, `tp1_price`, `tp2_price`, `max_loss_usd`, `reason="ALLOWED"` — write failures are silent (same rule as NFR-005) |

---

## Success Criteria

| ID | Criterion |
|----|-----------|
| SC-001 | Unit test: balance=10000, risk=1%, SL=20 pips → lot size matches formula to 2 decimal places |
| SC-002 | Unit test: drawdown=6% on 5% limit → `check_drawdown()` returns `TradeAllowedResult(allowed=False)` |
| SC-003 | Unit test: LONG entry=2350, D1_ATR=20, multiplier=1.5 → SL=2320.00, TP1=2395.00, TP2=2440.00 |
| SC-004 | Unit test: consecutive_losses=3 → recovery mode activates; lot size halved |
| SC-005 | Unit test: signal confidence=0.75, recovery_min_confidence=0.80 → signal rejected in recovery |
| SC-006 | Unit test: lot size never below 0.01 or above max_lot_size regardless of inputs |
| SC-007 | Unit test: SHORT direction → SL above entry, TP1 and TP2 below entry |
| SC-008 | `pytest --cov=src/risk` reports ≥ 80% coverage across all risk modules |
| SC-009 | No `MetaTrader5` import found in `src/risk/`: `grep -r "MetaTrader5\|import mt5" src/risk/` returns zero results |

---

## Out of Scope

- Trailing stop management (spec004 — Execution Engine, requires live MT5 tick stream)
- Basket recovery across multiple concurrent positions (post-MVP)
- ATR fetching from live data (ATR value passed in as parameter — caller's responsibility)
- Position closing logic (spec004 — Execution Engine)
- News filter / session detection (spec004 — Session & Filter System)
