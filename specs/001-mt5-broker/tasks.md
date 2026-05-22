# Tasks: MT5 Broker Connection

**Input**: Design documents from `specs/001-mt5-broker/`
**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/ ✅
**Branch**: `001-mt5-broker`
**Date**: 2026-05-11

**Organization**: Tasks grouped by User Story (P1→P4) for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallel-safe — different files, no inter-task dependency
- **[Story]**: Maps to User Story from spec.md (US1=Connection Auth, US2=Market Data, US3=Orders, US4=Health Monitor)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependencies and log infrastructure needed by all stories.

- [x] T001 Add `python-dotenv` to `requirements.txt` (needed by FR-017 `from_env()` factory) — already present at line 7
- [x] T002 [P] Create `.env.example` at project root with keys: `MT5_ACCOUNT`, `MT5_PASSWORD`, `MT5_SERVER` and placeholder values — document usage in comments
- [x] T003 [P] Verify `logs/` directory creation in `src/broker/order_manager.py:61` covers `connection_events.json` path — if not, add `Path("logs").mkdir(parents=True, exist_ok=True)` to `BrokerConnection.__init__()`

**Checkpoint**: `python-dotenv` installable, `.env.example` committed, `logs/` auto-created on startup.

---

## Phase 2: Foundational (Blocking Prerequisite)

**Purpose**: Timeout utility used by ALL three broker files. Must exist before US1/US2/US3 can add timeouts.

**⚠️ CRITICAL**: No user story timeout work can begin until T004 is complete.

- [x] T004 Add `_call_with_timeout(fn, timeout: float)` private method to `BrokerConnection` in `src/broker/connection.py` — uses `concurrent.futures.ThreadPoolExecutor`; raises `concurrent.futures.TimeoutError` on breach; import `ThreadPoolExecutor` and `TimeoutError as FuturesTimeoutError` at top of file

```python
# Shape of method to add (lines ~15–20 in connection.py after imports):
def _call_with_timeout(self, fn, timeout: float):
    with ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(fn).result(timeout=timeout)
```

**Checkpoint**: `_call_with_timeout` exists and is importable — unit test with a lambda that sleeps 2s confirms TimeoutError at 1s.

---

## Phase 3: User Story 1 — Broker Connection & Authentication (Priority: P1) 🎯 MVP

**Goal**: Trader starts system → connects and authenticates within 10s → credentials from `.env` only → every connection event saved to `logs/connection_events.json`.

**Independent Test**: Start system with valid `.env` → `logs/connection_events.json` contains `"event_type": "connected"` entry. Start with wrong password → file contains `"event_type": "failed"` and no trades placed.

### Unit Tests for US1 — write FIRST, confirm FAIL before implementing

- [x] T005 [P] [US1] Write `test_connect_success` in `tests/unit/test_broker_connection.py` — mock `mt5.initialize` → True, `mt5.login` → True; assert `conn.status == CONNECTED` and `conn.connect() == True`
- [x] T006 [P] [US1] Write `test_connect_auth_failure` — mock `mt5.login` → False; assert `conn.status == DISCONNECTED`, returns `False`, logs "Authentication Failed"
- [x] T007 [P] [US1] Write `test_connect_terminal_unavailable` — mock `mt5.initialize` → False; assert returns `False`, logs "Terminal Unavailable"
- [x] T008 [P] [US1] Write `test_connect_timeout` — mock `mt5.initialize` to sleep 11s; assert `FuturesTimeoutError` caught, returns `False`, logs "Connection Timeout"
- [x] T009 [P] [US1] Write `test_from_env_loads_credentials` — set env vars `MT5_ACCOUNT=111`, `MT5_PASSWORD=pass`, `MT5_SERVER=srv`; assert `BrokerConnection.from_env()` creates instance with correct `_account=111`
- [x] T010 [P] [US1] Write `test_event_persisted_to_file` — call `connect()` (mocked success); assert `logs/connection_events.json` exists and contains one entry with `"event_type": "connected"`
- [x] T010b [P] [US1] Write `test_credentials_absent_from_logs` in `tests/unit/test_broker_connection.py` — capture loguru output during failed `connect()` (wrong password); assert captured log string does NOT contain `MT5_PASSWORD` value or any substring of the password (NFR-001)

### Implementation for US1

- [x] T011 [US1] Add `from_env()` classmethod to `BrokerConnection` in `src/broker/connection.py` — call `load_dotenv()`, read `MT5_ACCOUNT` (cast to int), `MT5_PASSWORD`, `MT5_SERVER` from `os.environ`; raise `KeyError` with descriptive message if any key missing
- [x] T012 [US1] Add `_event_log_lock = threading.Lock()` class variable and `_event_log_path = Path("logs/connection_events.json")` class variable to `BrokerConnection` in `src/broker/connection.py`
- [x] T013 [US1] Add `_log_event_to_file(self, event: ConnectionEvent) -> None` method to `BrokerConnection` in `src/broker/connection.py` — read existing JSON array, append new entry `{event_type, timestamp, error_message}`, write back atomically under `_event_log_lock`; wrap entire write in `try/except OSError` — on failure log `WARNING "Event Log Write Failed — {error}"` and return without raising (trading must continue per spec edge case)
- [x] T014 [US1] Update `_record()` in `src/broker/connection.py` to call `self._log_event_to_file(event)` after appending to `self._events` list
- [x] T015 [US1] Wrap `mt5.initialize()` call in `connect()` with `self._call_with_timeout(mt5.initialize, timeout=10.0)` in `src/broker/connection.py` — catch `FuturesTimeoutError`, log "Connection Timeout — MT5 initialize did not respond within 10s", return `False`
- [x] T016 [US1] Wrap `mt5.login(...)` call in `connect()` with `self._call_with_timeout(lambda: mt5.login(self._account, self._password, self._server), timeout=10.0)` in `src/broker/connection.py` — same timeout/error handling pattern as T015

**Checkpoint**: Run `pytest tests/unit/test_broker_connection.py::test_connect_success tests/unit/test_broker_connection.py::test_from_env_loads_credentials tests/unit/test_broker_connection.py::test_event_persisted_to_file -v` — all 6 US1 tests PASS.

---

## Phase 4: User Story 2 — XAUUSD Market Data Fetch (Priority: P2)

**Goal**: After connection, system fetches live XAUUSD quote and 200-bar OHLCV for D1/H4/H1 — all calls return within 2 seconds or None with logged timeout.

**Independent Test**: Call `get_quote()` and `get_all_timeframes()` with MT5 mocked to hang → both return `None` within 2s with "Market Data Timeout" in logs.

### Unit Tests for US2 — write FIRST, confirm FAIL before implementing

- [x] T017 [P] [US2] Write `test_get_quote_timeout` in `tests/unit/test_broker_market_data.py` — mock `mt5.symbol_info_tick` to sleep 3s; assert `get_quote()` returns `None` within 2.5s and logs "Market Data Timeout"
- [x] T018 [P] [US2] Write `test_get_ohlcv_timeout` in `tests/unit/test_broker_market_data.py` — mock `mt5.copy_rates_from_pos` to sleep 3s; assert `get_ohlcv(Timeframe.H1)` returns `None` within 2.5s

### Implementation for US2

- [x] T019 [US2] Add `_call_with_timeout(fn, timeout: float)` module-level utility function in `src/broker/market_data.py` — same `ThreadPoolExecutor` pattern as `BrokerConnection._call_with_timeout` (standalone function since `MarketData` has no base class)
- [x] T020 [US2] Wrap `mt5.symbol_info_tick(SYMBOL)` in `get_quote()` with `_call_with_timeout(lambda: mt5.symbol_info_tick(SYMBOL), timeout=2.0)` in `src/broker/market_data.py` — catch `FuturesTimeoutError`, log "Market Data Timeout — symbol_info_tick did not respond within 2s", return `None`
- [x] T021 [US2] Wrap `mt5.copy_rates_from_pos(...)` in `get_ohlcv()` with `_call_with_timeout(lambda: mt5.copy_rates_from_pos(SYMBOL, timeframe.value, 0, count), timeout=2.0)` in `src/broker/market_data.py` — same error handling as T020

**Checkpoint**: Run `pytest tests/unit/test_broker_market_data.py -v` — all tests PASS including T017/T018.

---

## Phase 5: User Story 3 — Order Placement (Priority: P3)

**Goal**: SMC signal → order placed via MT5 with SL/TP → broker acknowledges within 5 seconds → all outcomes logged to `trades.json`.

**Independent Test**: Call `place_order()` with MT5 mocked to hang → returns `TradeOrder(result="timeout")` within 5.5s with "Order Timeout" in logs and entry written to `trades.json`.

### Unit Tests for US3 — write FIRST, confirm FAIL before implementing

- [x] T022 [P] [US3] Write `test_order_send_timeout` in `tests/unit/test_broker_order_manager.py` — mock `mt5.order_send` to sleep 6s; assert `place_order()` returns `TradeOrder` with `result="timeout"` within 5.5s and logs "Order Timeout — Status Unknown"
- [x] T023 [P] [US3] Write `test_order_timeout_logged_to_file` — confirm `logs/trades.json` receives entry with `result="timeout"` on timeout scenario

### Implementation for US3

- [x] T024 [US3] Add `_call_with_timeout(fn, timeout: float)` module-level utility in `src/broker/order_manager.py` — same `ThreadPoolExecutor` pattern
- [x] T024b [P] [US3] Write `test_margin_check_blocks_order` in `tests/unit/test_broker_order_manager.py` — mock `mt5.account_info()` returning `margin_level=8.0`; assert `place_order()` returns `TradeOrder(result="rejected")` with error message containing "Low Margin" and no `mt5.order_send` call made
- [x] T025 [US3] Add proactive margin check in `place_order()` in `src/broker/order_manager.py` — call `mt5.account_info()` before `order_send()`; if `margin_level < 10.0` log "Low Margin Warning — margin at {level}%, threshold 10%", set `result="rejected"`, log trade, return without submitting (FR-016)
- [x] T025b [US3] Wrap `mt5.order_send(request)` in `place_order()` with `_call_with_timeout(lambda: mt5.order_send(request), timeout=5.0)` in `src/broker/order_manager.py` — catch `FuturesTimeoutError`, set `order.result = "timeout"`, `order.error_message = "Order Timeout — Status Unknown; manual review required"`, log CRITICAL, call `self._log_trade(order)` before returning

**Checkpoint**: Run `pytest tests/unit/test_broker_order_manager.py -v` — all tests PASS including T022/T023.

---

## Phase 6: User Story 4 — Connection Health Monitoring & Recovery (Priority: P4)

**Goal**: System monitors connection every 10s → auto-reconnects on drop → enters emergency stop after 3 failures → `uptime_percent` property tracks session uptime for NFR-002.

**Independent Test**: Mock ping to fail 3 times → status == EMERGENCY_STOP, `logs/connection_events.json` has 3 "failed" entries and 1 "disconnected". Check `uptime_percent` returns float between 0.0–100.0.

### Unit Tests for US4 — write FIRST, confirm FAIL before implementing

- [x] T026 [P] [US4] Write `test_health_check_triggers_reconnect` in `tests/unit/test_broker_connection.py` — mock `_ping` → False; assert status transitions to RECONNECTING
- [x] T027 [P] [US4] Write `test_emergency_stop_after_3_failures` — mock all 3 reconnect attempts to fail; assert `status == EMERGENCY_STOP` and CRITICAL logged; assert total wall-clock elapsed time ≤ 35s (SC-005 — 30s budget + 5s tolerance)
- [x] T028 [P] [US4] Write `test_disconnect_clean` — call `disconnect()`; assert `mt5.shutdown` called, status == DISCONNECTED, `_stop_event` set
- [x] T029 [P] [US4] Write `test_uptime_percent` — mock `_session_start` = 100s ago, `_connected_seconds` = 90.0; assert `uptime_percent == 90.0`

### Implementation for US4

- [x] T030 [US4] Add `_session_start: Optional[datetime] = None` and `_connected_seconds: float = 0.0` fields to `BrokerConnection.__init__()` in `src/broker/connection.py`
- [x] T031 [US4] Set `self._session_start = datetime.utcnow()` at start of `connect()` in `src/broker/connection.py` (before MT5 initialize call)
- [x] T032 [US4] Update `_health_loop()` in `src/broker/connection.py` — on each successful ping (no loss detected), increment `self._connected_seconds += self.HEALTH_CHECK_INTERVAL`
- [x] T033 [US4] Add `uptime_percent` property to `BrokerConnection` in `src/broker/connection.py`
- [x] T034 [US4] Update `disconnect()` in `src/broker/connection.py` to log `uptime_percent` value: `logger.info(f"Session uptime: {self.uptime_percent}% — disconnecting")`

**Checkpoint**: Run `pytest tests/unit/test_broker_connection.py -v` — all 10 US1+US4 tests PASS.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, checklist update, quickstart verification.

- [x] T035 [P] Run full test suite `pytest -v` — confirm zero regressions across all unit and integration tests
  - Unit tests (40): PASSED — 2026-05-12
  - Integration tests (5): PASSED with live demo account 52878007 (ICMarketsSC-Demo) — 2026-05-12
  - Fix applied: `MT5_LOGIN` → `MT5_ACCOUNT` in integration test; `tests/integration/conftest.py` added to restore real MT5 over session mock
- [x] T036 [P] Update `specs/001-mt5-broker/checklists/implementation-review.md` — mark CHK017/018/019/020/021/022/026/033/034/035 as `[x]` (resolved)
- [x] T037 Verify `logs/connection_events.json` and `logs/trades.json` are listed in `.gitignore` — log files must not be committed
- [x] T038 [P] Run quickstart validation: follow `specs/001-mt5-broker/quickstart.md` step-by-step in paper trading mode — confirm all 3 commands succeed

**Checkpoint**: All tests green, checklist updated, logs gitignored, quickstart validated.

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)          → No dependencies — start immediately
Phase 2 (Foundational)   → Requires Phase 1 — BLOCKS all user stories
Phase 3 (US1 P1)         → Requires Phase 2 — start here for MVP
Phase 4 (US2 P2)         → Requires Phase 2 — can run parallel to US1
Phase 5 (US3 P3)         → Requires Phase 2 — can run parallel to US1/US2
Phase 6 (US4 P4)         → Requires US1 complete (uptime tracks connection)
Phase 7 (Polish)         → Requires all stories complete
```

### User Story Dependencies

- **US1 (P1)**: After Phase 2 — no story dependencies — **start here**
- **US2 (P2)**: After Phase 2 — independent of US1
- **US3 (P3)**: After Phase 2 — independent of US1/US2
- **US4 (P4)**: After US1 complete — uptime property builds on connection fields

### Parallel Opportunities per Story

**US1** — T005, T006, T007, T008, T009, T010 (all 6 unit tests) can run in parallel before any implementation.

**US2** — T017, T018 (both timeout tests) can run in parallel.

**US3** — T022, T023 (both order tests) can run in parallel.

**US4** — T026, T027, T028, T029 (all 4 tests) can run in parallel.

---

## Implementation Strategy

### MVP (US1 Only — minimum to prove connection works)

1. Phase 1: Setup (T001–T003)
2. Phase 2: Foundational (T004)
3. Phase 3: US1 tests T005–T010 (write + confirm FAIL)
4. Phase 3: US1 impl T011–T016
5. **STOP + VALIDATE**: 6 US1 tests GREEN, `connection_events.json` written, `from_env()` works

### Full Delivery (all 4 stories)

```
Phase 1 → Phase 2 → US1 → US2 → US3 → US4 → Polish
```

### Task Count Summary

| Phase | Tasks | Tests | Impl |
|---|---|---|---|
| Setup | 3 | — | 3 |
| Foundational | 1 | — | 1 |
| US1 (P1) | 12 | 6 | 6 |
| US2 (P2) | 5 | 2 | 3 |
| US3 (P3) | 4 | 2 | 2 |
| US4 (P4) | 9 | 4 | 5 |
| Polish | 4 | — | 4 |
| **Total** | **38** | **14** | **24** |

---

## Notes

- Tests marked `[P]` run in parallel — all read different mock state, no shared file
- Each story has independent test criteria — validate before moving to next priority
- `_call_with_timeout` appears in 3 files — keep as module-level function (not shared util) to avoid cross-module dependency
- Commit after each Phase checkpoint — allows clean rollback per story
