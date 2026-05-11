# Data Model: MT5 Broker Connection

**Feature**: 001-mt5-broker
**Date**: 2026-05-11

---

## Entities

### 1. ConnectionStatus (Enum)
```
DISCONNECTED   — Not connected; initial state and after clean shutdown
CONNECTING     — connect() call in progress
CONNECTED      — Authenticated and active
RECONNECTING   — Health check failed; reconnect loop running
EMERGENCY_STOP — 3 consecutive reconnect failures; manual intervention required
```
**Transitions**:
```
DISCONNECTED → CONNECTING → CONNECTED → RECONNECTING → CONNECTED (success)
                                                      → EMERGENCY_STOP (3 failures)
CONNECTED → DISCONNECTED (clean shutdown)
```

---

### 2. ConnectionEvent
| Field | Type | Constraint |
|---|---|---|
| event_type | str | one of: connected / disconnected / reconnected / failed |
| timestamp | datetime | UTC, auto-set |
| error_message | Optional[str] | null unless event_type = failed |
| uptime_percent | Optional[float] | set on disconnect events only |

**Persistence**: `logs/connection_events.json` — append-only, atomic write

---

### 3. BrokerConnection (updated)
| Field | Type | Source |
|---|---|---|
| _account | int | `.env` MT5_ACCOUNT |
| _password | str | `.env` MT5_PASSWORD (never logged) |
| _server | str | `.env` MT5_SERVER |
| _status | ConnectionStatus | runtime state |
| _session_start | Optional[datetime] | set on first connect() |
| _connected_seconds | float | accumulated by health monitor |
| _stop_event | threading.Event | controls health thread lifecycle |
| _events | list[ConnectionEvent] | in-memory + persisted to file |

**New methods**:
- `from_env() → BrokerConnection` — factory; loads credentials from `.env`
- `uptime_percent → float` — NFR-002 measurement
- `_log_event_to_file(event)` — persists to `logs/connection_events.json`

---

### 4. MarketQuote
| Field | Type | Constraint |
|---|---|---|
| symbol | str | always "XAUUSD" |
| bid | float | > 0 |
| ask | float | > bid |
| spread_points | int | ≤ max_spread_points |
| timestamp | datetime | UTC tick time |

**Returns None when**: market closed OR spread > threshold (caller must handle both)

---

### 5. TradeOrder
| Field | Type | Constraint |
|---|---|---|
| order_type | str | "BUY" or "SELL" |
| entry_price | float | live ask (BUY) or bid (SELL) at submission |
| stop_loss | float | BUY: sl < price; SELL: sl > price |
| take_profit | float | BUY: tp > price; SELL: tp < price |
| volume | float | > 0, set by risk manager |
| magic_number | int | 202605 (config.yaml) |
| timestamp | str | ISO-8601 UTC |
| result | str | pending / success / failed / rejected |
| broker_ticket | Optional[int] | set on success |
| error_message | Optional[str] | set on failure/rejection |
| max_loss_usd | Optional[float] | calculated pre-submission |

**Persistence**: `logs/trades.json` — append-only, atomic write, thread-safe

---

## State Machine: BrokerConnection

```
                    ┌─────────────────────────────────────┐
                    │                                     │
             connect() success                    health ping ok
                    │                                     │
  ┌──────────┐    ┌─────────────┐    ping fail    ┌──────────────┐
  │DISCONNECT│───▶│  CONNECTING │                 │  RECONNECTING│
  │   (init) │    └─────────────┘                 └──────────────┘
  └──────────┘           │                               │
        ▲                │ success                       │ 3 failures
        │                ▼                               ▼
        │         ┌─────────────┐              ┌──────────────────┐
        └─────────│  CONNECTED  │              │  EMERGENCY_STOP  │
    disconnect()  └─────────────┘              │ (manual reset)   │
                                               └──────────────────┘
```

---

## Validation Rules

| Rule | Entity | Enforcement |
|---|---|---|
| SL must be below entry for BUY | TradeOrder | `_sl_tp_valid()` pre-submission |
| SL must be above entry for SELL | TradeOrder | `_sl_tp_valid()` pre-submission |
| SL and TP must be non-zero | TradeOrder | `_sl_tp_valid()` — zero = invalid |
| Spread ≤ max_spread_points | MarketQuote | `get_quote()` returns None if exceeded |
| Credentials never logged | BrokerConnection | Only error code logged, not password |
| Events persisted atomically | ConnectionEvent | File lock on every write |
