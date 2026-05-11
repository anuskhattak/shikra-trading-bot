# Implementation Plan: MT5 Broker Connection

**Branch**: `001-mt5-broker` | **Date**: 2026-05-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/001-mt5-broker/spec.md`

---

## Summary

Build a production-grade MetaTrader 5 broker connection layer for XAUUSD trading. The layer handles authentication (credentials from `.env` only), live market data fetch with spread guard, market order placement with mandatory SL/TP, and continuous connection health monitoring with auto-reconnect. All gaps identified in the implementation review checklist will be resolved: connection event persistence, call timeouts, non-blocking I/O, and full unit test coverage for `BrokerConnection`.

---

## Technical Context

**Language/Version**: Python 3.10+
**Primary Dependencies**: MetaTrader5, loguru, pandas, python-dotenv, concurrent.futures (stdlib)
**Storage**: `logs/trades.json` (orders), `logs/connection_events.json` (connection events) — append-only JSON, atomic writes
**Testing**: pytest, unittest.mock (MT5 mocked in unit tests; live terminal in integration tests)
**Target Platform**: Windows 10+ with MT5 terminal on same machine (NFR-004)
**Project Type**: Single project — `src/broker/` module
**Performance Goals**:
- Connection established ≤ 10s (SC-001)
- Market data returned ≤ 2s (SC-002)
- Order acknowledged ≤ 5s (SC-004)
- Connection uptime ≥ 99% during active sessions (NFR-002)
**Constraints**:
- Credentials NEVER appear in any log (NFR-001)
- All MT5 I/O blocking with timeout — never hangs indefinitely (NFR-003)
- Atomic log writes — no partial entries (NFR-005)
- Windows-only; Unix `signal.alarm` timeout NOT available

---

## Constitution Check

*From CLAUDE.md project rules — checked against current spec + research.*

| Gate | Status | Notes |
|---|---|---|
| Signal Integrity | ✅ PASS | Broker layer — no signal logic in scope |
| Risk First — SL/TP enforced | ✅ PASS | `_sl_tp_valid()` rejects invalid geometry pre-submission |
| Risk First — Margin check | ⚠️ PARTIAL | Reactive (RETCODE) only; proactive check deferred to Risk Manager feature |
| Auditability — Order log | ✅ PASS | `trades.json` — all fields, atomic write |
| Auditability — Connection log | ❌ FAIL | Events in-memory only → **must fix: FR-008** |
| Quality Gates — Unit tests | ❌ FAIL | `BrokerConnection` has no unit tests → **must fix: FR-018** |
| Documentation | ✅ PASS | Docstrings on all public methods |
| Credentials masked | ✅ PASS | Only error code logged, never password |

**Gate violations to fix in this plan**: FR-008 (event persistence), FR-018 (unit tests), NFR-003 (non-blocking), timeout enforcement (SC-001/002/004).

---

## Project Structure

### Documentation (this feature)

```text
specs/001-mt5-broker/
├── plan.md                  # This file
├── research.md              # Phase 0 — all unknowns resolved
├── data-model.md            # Phase 1 — entities and state machine
├── quickstart.md            # Phase 1 — setup and usage guide
├── contracts/
│   └── broker_interface.py  # Phase 1 — abstract broker protocol
├── checklists/
│   ├── requirements.md      # Spec quality checklist (existing)
│   └── implementation-review.md  # Implementation gap checklist
└── tasks.md                 # Phase 2 — /sp.tasks output (not yet created)
```

### Source Code

```text
src/broker/
├── __init__.py
├── connection.py       — BrokerConnection (add: from_env, timeout, event file log, uptime)
├── market_data.py      — MarketData (add: non-blocking wrapper, timeout)
└── order_manager.py    — OrderManager (add: non-blocking wrapper, timeout)

tests/
├── unit/
│   ├── test_broker_connection.py      — NEW: FR-018 unit tests
│   ├── test_broker_market_data.py     — existing
│   └── test_broker_order_manager.py  — existing
└── integration/
    └── test_mt5_connection.py         — existing

logs/
├── trades.json              — existing
└── connection_events.json   — NEW: FR-008 persistent event log
```

---

## Phase 0: Research Findings

All NEEDS CLARIFICATION items resolved. See [research.md](research.md) for full analysis.

| ID | Decision |
|---|---|
| R-001 | Timeouts via `ThreadPoolExecutor.submit().result(timeout=N)` |
| R-002 | Non-blocking via shared `ThreadPoolExecutor` for all MT5 I/O |
| R-003 | Credentials via `from_env()` factory + `python-dotenv` |
| R-004 | Connection events → `logs/connection_events.json` atomic append |
| R-005 | Uptime via wall-clock counters + `uptime_percent` property |

---

## Phase 1: Implementation Design

### Change 1 — `connection.py`: Persist Events to File (FR-008)

Add `_log_event_to_file()` method. Append `ConnectionEvent` as JSON to `logs/connection_events.json` using a class-level `threading.Lock()` — same pattern as `_log_trade()`.

```python
_event_log_lock = threading.Lock()
_event_log_path = Path("logs/connection_events.json")

def _log_event_to_file(self, event: ConnectionEvent) -> None:
    entry = {"event_type": event.event_type,
             "timestamp": event.timestamp.isoformat(),
             "error_message": event.error_message}
    with self._event_log_lock:
        records = []
        if self._event_log_path.exists() and self._event_log_path.stat().st_size > 0:
            with open(self._event_log_path, "r") as fh:
                records = json.load(fh)
        records.append(entry)
        with open(self._event_log_path, "w") as fh:
            json.dump(records, fh, indent=2, default=str)
```

Call `_log_event_to_file(event)` inside `_record()` after appending to `self._events`.

---

### Change 2 — `connection.py`: Add Timeout to `connect()` (SC-001)

Wrap `mt5.initialize()` and `mt5.login()` in `ThreadPoolExecutor` with 10-second timeout.

```python
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

def _call_with_timeout(self, fn, timeout: float):
    with ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(fn)
        return future.result(timeout=timeout)
```

Replace direct `mt5.initialize()` and `mt5.login()` calls with `_call_with_timeout(fn, timeout)`. On `FuturesTimeoutError`, log "Connection Timeout" and return `False`.

---

### Change 3 — `connection.py`: Add `from_env()` Factory (FR-017)

```python
@classmethod
def from_env(cls) -> "BrokerConnection":
    from dotenv import load_dotenv
    load_dotenv()
    account = int(os.environ["MT5_ACCOUNT"])
    password = os.environ["MT5_PASSWORD"]
    server = os.environ["MT5_SERVER"]
    return cls(account, password, server)
```

---

### Change 4 — `connection.py`: Add Uptime Measurement (NFR-002)

Add `_session_start`, `_connected_seconds` fields. Health monitor increments `_connected_seconds` each passing ping. Expose `uptime_percent` property. Log uptime on disconnect.

---

### Change 5 — `market_data.py`: Add Timeout (SC-002)

Wrap `mt5.symbol_info_tick()` and `mt5.copy_rates_from_pos()` with 2-second timeout using `_call_with_timeout`. Return `None` on timeout with log "Market Data Timeout".

---

### Change 6 — `order_manager.py`: Add Timeout + Proactive Margin Check (SC-004, FR-016)

**Proactive margin check** (FR-016 — spec requires check BEFORE submission):
```python
info = mt5.account_info()
if info is not None and info.margin_level and info.margin_level < 10.0:
    logger.error(f"Low Margin Warning — margin at {info.margin_level:.1f}%, threshold 10%")
    order.result = "rejected"
    order.error_message = f"Low Margin — {info.margin_level:.1f}% < 10% threshold"
    self._log_trade(order)
    return order
```

**Timeout** on `mt5.order_send()` with 5-second limit. On `FuturesTimeoutError`, log "Order Timeout — Status Unknown" and return `TradeOrder` with `result="timeout"`.

---

### Change 7 — `tests/unit/test_broker_connection.py`: New Unit Tests (FR-018)

Test scenarios (all with mocked `mt5`):
1. `test_connect_success` — mt5.initialize + login return True → status = CONNECTED
2. `test_connect_auth_failure` — login returns False → status = DISCONNECTED, returns False
3. `test_connect_terminal_unavailable` — initialize returns False → "Terminal Unavailable" logged
4. `test_connect_timeout` — initialize hangs 11s → FuturesTimeoutError raised → returns False
5. `test_health_check_triggers_reconnect` — ping returns False → status = RECONNECTING
6. `test_emergency_stop_after_3_failures` — 3 failed reconnects → status = EMERGENCY_STOP
7. `test_disconnect_clean` — disconnect() calls mt5.shutdown(), status = DISCONNECTED
8. `test_event_persisted_to_file` — connect() → connection_events.json written
9. `test_uptime_percent` — connected 90s out of 100s → uptime = 90.0%
10. `test_from_env_loads_credentials` — .env vars set → from_env() returns correct account

---

## Complexity Tracking

No constitution violations requiring justification. All changes are direct additions to existing files — no new abstractions, no new project structure.

---

## Acceptance Checks

- [ ] FR-008: `logs/connection_events.json` written on every connect/disconnect/reconnect/fail event
- [ ] FR-017: `from_env()` factory exists; raw constructor still works for tests
- [ ] FR-018: 10 unit tests in `test_broker_connection.py` — all passing
- [ ] SC-001: `connect()` raises no hang — times out within 10s if MT5 unresponsive
- [ ] SC-002: `get_quote()` returns within 2s or None with timeout log
- [ ] SC-004: `place_order()` returns within 5s or TradeOrder with result="timeout"
- [ ] NFR-002: `uptime_percent` property accessible, logs on disconnect
- [ ] NFR-003: MT5 calls run in thread pool — main thread not blocked
- [ ] All existing tests still pass (no regression)
