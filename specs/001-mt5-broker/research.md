# Phase 0 Research: MT5 Broker Connection

**Feature**: 001-mt5-broker
**Date**: 2026-05-11
**Purpose**: Resolve all NEEDS CLARIFICATION items before Phase 1 design

---

## R-001: Timeout on Blocking MT5 Calls (SC-001, SC-002, SC-004)

**Problem**: `mt5.initialize()`, `mt5.login()`, and `mt5.order_send()` are C extension calls — no native timeout parameter. System can hang indefinitely if terminal or broker is unresponsive.

**Decision**: Wrap each blocking call in `concurrent.futures.ThreadPoolExecutor.submit().result(timeout=N)`.

```python
from concurrent.futures import ThreadPoolExecutor, TimeoutError

with ThreadPoolExecutor(max_workers=1) as ex:
    future = ex.submit(mt5.initialize)
    result = future.result(timeout=10)  # raises TimeoutError if > 10s
```

**Rationale**: Cleanest pattern for adding timeout to synchronous blocking code without refactoring the call itself. Works with any C extension.

**Alternatives Rejected**:
- `threading.Timer` — cancels after deadline but doesn't interrupt the blocked thread; call still runs
- `asyncio.wait_for` — requires full async refactor of all callers (too invasive for this feature)
- `signal.alarm` — Unix only; does not work on Windows 10 (NFR-004 violation)

---

## R-002: Non-Blocking Architecture for NFR-003

**Problem**: `get_ohlcv()`, `place_order()`, and `connect()` all block the calling thread. Spec (NFR-003) requires non-blocking operations so system responsiveness does not degrade.

**Decision**: Run all MT5 I/O in a shared `ThreadPoolExecutor` (thread pool). Callers receive a `Future` they can await or check.

**Architecture**:
```
Main thread (signal engine loop)
    ↓ submits task
ThreadPoolExecutor (MT5 I/O thread)
    ↓ result available
Main thread resumes (non-blocked)
```

**Rationale**: MT5 Python API is a C extension — cannot be made natively async. Thread pool is the standard Python pattern for non-blocking I/O on blocking APIs.

**Alternatives Rejected**:
- Full `asyncio` — MT5 C extension releases the GIL inconsistently; `run_in_executor` adds complexity for marginal gain
- `multiprocessing` — heavy overhead; MT5 terminal connection is per-process, complicates shared state

---

## R-003: Credentials from .env Only (FR-017)

**Problem**: `BrokerConnection.__init__()` currently accepts raw `account`, `password`, `server` values. Spec FR-017 requires credentials come exclusively from `.env`.

**Decision**: Add `BrokerConnection.from_env()` factory classmethod. Constructor remains available for tests (with mock values). Production entry point MUST use `from_env()`.

```python
@classmethod
def from_env(cls) -> "BrokerConnection":
    load_dotenv()
    account = int(os.environ["MT5_ACCOUNT"])
    password = os.environ["MT5_PASSWORD"]
    server = os.environ["MT5_SERVER"]
    return cls(account, password, server)
```

**.env format**:
```
MT5_ACCOUNT=12345678
MT5_PASSWORD=your_password_here
MT5_SERVER=BrokerName-Server
```

**Rationale**: Factory pattern separates credential loading from connection logic. Constructor stays injectable for unit tests (no live `.env` needed in CI).

**Alternatives Rejected**:
- Config YAML — YAML files accidentally committed to git more often than `.env`
- Hashicorp Vault / AWS Secrets — overkill for single-machine Windows trading setup
- Environment variables only (no `.env` file) — requires manual export on every session

---

## R-004: Persistent Connection Event Log (FR-008)

**Problem**: `_record()` appends to `self._events` in memory only — lost on restart, no audit trail.

**Decision**: Add `_log_event_to_file()` that appends `ConnectionEvent` to `logs/connection_events.json` using same atomic lock + read-modify-write pattern as `trades.json`.

**Log entry format**:
```json
{
  "event_type": "connected",
  "timestamp": "2026-05-11T08:30:00.000000",
  "error_message": null
}
```

**Rationale**: Consistent with existing `_log_trade()` pattern in `order_manager.py`. Same atomic lock guarantees no partial entries (NFR-005 extension).

**Alternatives Rejected**:
- `logging` module file handler — not JSON, harder to parse programmatically for audit
- SQLite — overkill; simple append log is sufficient for connection events
- Separate `.log` text file — inconsistent with `trades.json` format; two different formats to maintain

---

## R-005: Connection Uptime Measurement (NFR-002)

**Problem**: NFR-002 requires ≥ 99% uptime during active sessions but no measurement exists.

**Decision**: Track wall-clock durations using `datetime` counters in `BrokerConnection`. Expose `uptime_percent` property.

```python
@property
def uptime_percent(self) -> float:
    total = (datetime.utcnow() - self._session_start).total_seconds()
    if total == 0:
        return 100.0
    return round((self._connected_seconds / total) * 100, 2)
```

**Counters to add**:
- `_session_start: datetime` — set on first `connect()` call
- `_connected_seconds: float` — accumulated while status = CONNECTED
- Health monitor loop increments `_connected_seconds` by `HEALTH_CHECK_INTERVAL` each passing ping

**Rationale**: Zero external dependencies. Simple and auditable. Uptime logged to connection_events.json on disconnect.

**Alternatives Rejected**:
- Prometheus + Grafana — out of scope for single-machine setup; infrastructure overkill
- External uptime monitoring service — requires internet, introduces external dependency

---

## Summary: All NEEDS CLARIFICATION Resolved

| Item | Resolution |
|---|---|
| Timeout mechanism | `ThreadPoolExecutor.submit().result(timeout=N)` |
| Non-blocking pattern | Shared `ThreadPoolExecutor` for all MT5 I/O |
| Credentials source | `from_env()` factory + `python-dotenv` |
| Event persistence | `logs/connection_events.json` — same atomic pattern |
| Uptime measurement | Wall-clock counters + `uptime_percent` property |
