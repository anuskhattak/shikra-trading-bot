# Quickstart: Execution Engine (spec005)

**Branch**: `005-execution-engine` | **Date**: 2026-05-20

---

## What Is Being Built

`src/execution/` — the final stage of the Shikra trading pipeline. It:
1. Receives a validated `ExecutionSignal` (EntrySignal + RiskCalculation)
2. Runs pre-flight safety checks (kill-switch, pyramiding, drawdown, margin, min-stop)
3. Places a XAUUSD market order with SL + TP via `OrderManager`
4. Tracks the open position (trailing stop, partial close at TP1, full close at TP2)
5. Logs every action to `logs/trades.json`

---

## Pipeline Position

```
SMC Engine (spec002)
       │  EntrySignal
       ▼
Filter Pipeline (spec004)
       │  TradeGateResult (ALLOWED)
       ▼
Risk Manager (spec003)
       │  RiskCalculation
       ▼
ExecutionEngine.execute_signal(ExecutionSignal)
       │
       ├── Pre-flight checks ──── REJECTED → audit log → stop
       │
       ├── OrderManager.place_order() ──── MT5 broker
       │         │
       │         ▼
       │    PositionState stored in engine
       │
       └── (on each H1 bar)
           ExecutionEngine.manage_open_positions()
               ├── trailing stop update
               ├── partial close at TP1
               └── full close at TP2 / detect external close
```

---

## New Files

```
src/execution/
├── __init__.py           — public exports
├── models.py             — ExecutionSignal, PositionState, TradeAuditEntry, KillSwitchState, AuditAction
├── preflight.py          — run_preflight() + individual check functions
├── position_manager.py   — manage_positions(), evaluate_trailing_stop(), apply_partial_close(), reconcile_positions()
├── audit_logger.py       — write_audit_entry(), write_audit_entries()
├── kill_switch.py        — activate_kill_switch(), deactivate_kill_switch(), is_kill_switch_active()
└── execution_engine.py   — ExecutionEngine class (execute_signal, manage_open_positions)

tests/unit/
├── test_execution_preflight.py
├── test_execution_position_manager.py
├── test_execution_audit_logger.py
├── test_execution_kill_switch.py
└── test_execution_engine.py

tests/integration/
└── test_execution_integration.py

logs/
└── kill_switch.json      — created on first activate; absent = inactive
```

---

## Dependencies

| Package | Already Present | Required For |
|---------|----------------|--------------|
| `MetaTrader5` | Yes (spec001) | Broker calls |
| `loguru` | Yes (spec001) | Logging |
| `pytest` | Yes | Tests |
| `pytest-mock` | Likely yes | Mock MT5 in unit tests |
| `uuid` | stdlib | Signal/audit IDs |
| `json`, `pathlib`, `threading` | stdlib | Audit log, kill-switch |

No new pip packages required.

---

## Config Changes (`config.yaml`)

Add to existing `config.yaml`:

```yaml
execution:
  trailing:
    activation_distance: 30.0
    trailing_distance: 20.0
  partial_close:
    tp1_close_ratio: 0.5
  magic_number: 20250519
  slippage_points: 5
  kill_switch_path: "logs/kill_switch.json"
  audit_log_path: "logs/trades.json"
```

---

## Usage (Main Loop Sketch)

```python
from src.execution import ExecutionEngine, ExecutionSignal, activate_kill_switch
from src.broker.order_manager import OrderManager
import uuid
from datetime import datetime, timezone

order_manager = OrderManager(magic_number=config["execution"]["magic_number"])
engine = ExecutionEngine(order_manager=order_manager, config=config["execution"])

# On each new validated signal:
exec_signal = ExecutionSignal(
    entry_signal=entry_signal,          # from spec002
    risk_calc=risk_calc,                # from spec003 (lot_size must be > 0)
    signal_id=str(uuid.uuid4()),
    received_at=datetime.now(timezone.utc),
)
audit_entry = engine.execute_signal(
    exec_signal,
    day_start_equity=risk_state.day_start_equity,
    current_equity=current_equity,
)

# On each H1 bar close:
audit_entries = engine.manage_open_positions(
    current_prices={"XAUUSD": current_bid_or_ask}
)

# Emergency stop (from CLI or monitoring script):
activate_kill_switch(reason="Manual operator halt")
```

---

## Running Tests

```bash
# Unit tests only (no MT5 required)
pytest tests/unit/test_execution_*.py -v

# Integration test (requires MT5 demo connection)
pytest tests/integration/test_execution_integration.py -v

# Coverage check (must be >= 80%)
pytest tests/unit/test_execution_*.py --cov=src/execution --cov-report=term-missing
```

---

## Kill-Switch Operations

```bash
# Activate from terminal (emergency stop):
python -c "from src.execution import activate_kill_switch; activate_kill_switch(reason='Manual halt')"

# Deactivate:
python -c "from src.execution import deactivate_kill_switch; deactivate_kill_switch()"

# Check status:
python -c "from src.execution import is_kill_switch_active; print(is_kill_switch_active())"
```

---

## Audit Log Format (`logs/trades.json`)

Every action appended as one JSON object in the array:

```json
[
  {
    "audit_id": "a1b2c3d4-...",
    "timestamp_utc": "2026-05-20T10:30:00.000Z",
    "action_type": "ORDER_PLACED",
    "signal_id": "uuid-of-exec-signal",
    "ticket_id": 123456789,
    "direction": "LONG",
    "lot_size": 0.05,
    "requested_entry_price": 3312.50,
    "actual_fill_price": 3312.52,
    "sl_price": 3282.50,
    "tp1_price": 3357.50,
    "tp2_price": 3402.50,
    "exit_price": null,
    "realised_pnl": null,
    "rejection_reason": null,
    "new_sl_price": null
  }
]
```
