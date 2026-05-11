# Implementation Review Checklist: MT5 Broker Connection

**Purpose**: Track which spec requirements are implemented in code vs missing — "kiya kaam kar raha hai or kiya nahi"
**Created**: 2026-05-11
**Feature**: [spec.md](../spec.md)
**Code Under Review**: `src/broker/connection.py`, `src/broker/market_data.py`, `src/broker/order_manager.py`

**Legend**: `[x]` = Done | `[ ]` = Missing | `[~]` = Partial / Gap

---

## Functional Requirements — Connection & Authentication

- [x] CHK001 — FR-001: System connects to MT5 terminal using credentials from config — `BrokerConnection.__init__()` accepts account/password/server [Spec §FR-001]
- [x] CHK002 — FR-002: Authentication uses account number, password, and server name — `mt5.login(account, password, server)` called in `connect()` [Spec §FR-002]
- [x] CHK003 — FR-003: No market data or order operations proceed without successful authentication — `connect()` returns `False` on auth failure, caller must gate on this [Spec §FR-003]
- [x] CHK004 — FR-013: Clean shutdown disconnects MT5 without orphaned connections — `disconnect()` calls `mt5.shutdown()` and stops health thread [Spec §FR-013]
- [x] CHK005 — FR-014: Connection status exposed at all times — `status` property returns `ConnectionStatus` enum (Connected/Disconnected/Reconnecting/EmergencyStop) [Spec §FR-014]

---

## Functional Requirements — Market Data

- [x] CHK006 — FR-004: Current XAUUSD bid, ask, spread returned on demand — `MarketData.get_quote()` returns `MarketQuote` dataclass [Spec §FR-004]
- [x] CHK007 — FR-005: Historical OHLCV for D1, H4, H1 with minimum 200 bars — `get_ohlcv()` enforces `MIN_BARS = 200` and rejects partial data [Spec §FR-005]
- [x] CHK008 — FR-015: Order skipped when spread exceeds max threshold — `get_quote()` returns `None` and logs "High Spread — Trade Skipped" [Spec §FR-015]

---

## Functional Requirements — Order Placement

- [x] CHK009 — FR-006: Market orders placed with mandatory SL and TP — `place_order()` requires both `stop_loss` and `take_profit` params [Spec §FR-006]
- [x] CHK010 — FR-007: Orders rejected when SL or TP is absent/invalid — `_sl_tp_valid()` rejects zero values and wrong-side geometry; logs "Missing SL/TP — Order Rejected" [Spec §FR-007]
- [x] CHK011 — FR-009: Every order attempt logged with entry, SL, TP, volume, result — `_log_trade()` writes complete `TradeOrder` record to `logs/trades.json` [Spec §FR-009]
- [x] CHK012 — FR-016: Insufficient margin handled — `TRADE_RETCODE_NO_MONEY` caught, logs "Insufficient Margin", order not placed [Spec §FR-016]

---

## Functional Requirements — Health Monitoring & Recovery

- [x] CHK013 — FR-010: Connection loss detected within 10 seconds — `HEALTH_CHECK_INTERVAL = 10` in health monitor loop [Spec §FR-010]
- [x] CHK014 — FR-011: Automatic reconnection attempted after connection loss — `_reconnect_loop()` runs up to 3 attempts [Spec §FR-011]
- [x] CHK015 — FR-012: All trading halted during reconnection — status set to `RECONNECTING` before reconnect loop starts [Spec §FR-012]
- [x] CHK016 — SC-008: Emergency stop after 3 consecutive failed reconnections — `_reconnect_loop()` sets `EMERGENCY_STOP` status and logs CRITICAL alert [Spec §SC-008]

---

## GAPS — Requirements in Spec but NOT Implemented

- [ ] CHK017 — FR-008 GAP: Connection events are only stored in-memory `_events` list — NOT written to a persistent log file. Spec requires durable, timestamped log. `_record()` appends to `self._events[]` but never writes to disk [Gap, Spec §FR-008]
- [ ] CHK018 — SC-001 GAP: No timeout enforced on `connect()` — if MT5 terminal hangs, the call blocks indefinitely. Spec requires connection within 10 seconds [Gap, Spec §SC-001]
- [ ] CHK019 — SC-002 GAP: No timeout enforced on `get_quote()` — if MT5 tick API stalls, call blocks. Spec requires price data within 2 seconds [Gap, Spec §SC-002]
- [ ] CHK020 — SC-004 GAP: No timeout enforced on `mt5.order_send()` — if broker is slow, call blocks. Spec requires order acknowledgment within 5 seconds [Gap, Spec §SC-004]
- [ ] CHK021 — NFR-003 GAP: All operations are synchronous/blocking — `connect()`, `get_ohlcv()`, `order_send()` all block the calling thread. Spec requires non-blocking operations [Gap, Spec §NFR-003]
- [ ] CHK022 — NFR-002 GAP: No uptime measurement or alerting mechanism implemented. Spec requires ≥ 99% connection uptime during active sessions [Gap, Spec §NFR-002]
- [~] CHK023 — FR-016 PARTIAL: Margin check is reactive only (handles RETCODE after submission). Spec implies proactive check before order submission when margin is "critically low" [Ambiguity, Spec §FR-016, Edge Case §6]

---

## Non-Functional Requirements — Security

- [x] CHK024 — NFR-001: Credentials never appear in logs — password not passed to any logger call; only numeric error code logged on auth failure [Spec §NFR-001]
- [x] CHK025 — NFR-005: trades.json writes are atomic — `_log_lock` serializes all concurrent writes; no partial JSON entries possible [Spec §NFR-005]
- [ ] CHK026 — NFR-001 GAP: Is there a requirement that credentials sourced from `.env` are validated (not hardcoded) at system startup? Spec assumes `.env` loading but `BrokerConnection` constructor accepts raw values with no validation of source [Gap, Spec §Assumptions]

---

## Ambiguities in Requirements

- [~] CHK027 — AMBIGUITY: `get_quote()` returns `None` for both "market closed" AND "high spread" scenarios — caller cannot distinguish between them. Are separate return values or status codes required? [Ambiguity, Spec §FR-004, FR-015]
- [~] CHK028 — AMBIGUITY: FR-016 says "halt order placement when account margin falls below a safe operating level" — the threshold is not defined in spec. What is the minimum safe margin level %? [Ambiguity, Spec §FR-016]
- [~] CHK029 — AMBIGUITY: SC-005 says "reconnect within 30 seconds" — current implementation does 3 attempts × 10 sec pause = 30 sec. But each attempt itself takes time. Total time could exceed 30s under slow network. Is the 30s wall-clock or net wait time? [Ambiguity, Spec §SC-005]

---

## Test Coverage Status

- [x] CHK030 — Integration test exists for MT5 connection — `tests/integration/test_mt5_connection.py` [Coverage]
- [x] CHK031 — Unit test exists for order manager — `tests/unit/test_broker_order_manager.py` [Coverage]
- [x] CHK032 — Unit test exists for market data — `tests/unit/test_broker_market_data.py` [Coverage]
- [ ] CHK033 — No unit test for `BrokerConnection` class itself — `connection.py` has no corresponding unit test file [Gap, Coverage]
- [ ] CHK034 — No test for emergency stop scenario (3 consecutive reconnect failures) [Gap, Coverage]
- [ ] CHK035 — No test for in-flight order during connection drop (SC edge case) [Gap, Coverage]

---

## Summary

| Category | Total | Done ✅ | Partial ⚠️ | Missing ❌ |
|---|---|---|---|---|
| Functional Requirements | 16 | 13 | 1 | 2 |
| Non-Functional Requirements | 5 | 2 | 0 | 3 |
| Success Criteria | 10 | 7 | 1 | 2 |
| Test Coverage | 6 | 3 | 0 | 3 |
| **Total** | **37** | **25 (68%)** | **2 (5%)** | **10 (27%)** |

### Top Priority Gaps (Fix Before Live Trading)

1. **CHK017** — Connection events not persisted to file (FR-008) — audit trail broken
2. **CHK018/19/20** — No timeouts on connect/data/order calls — system can hang indefinitely
3. **CHK021** — Blocking operations violate NFR-003 — system freezes during slow broker response
4. **CHK026** — No validation that credentials come from `.env` — hardcoded secret risk
