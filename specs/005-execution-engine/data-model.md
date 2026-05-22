# Data Model: Execution Engine (spec005)

**Branch**: `005-execution-engine` | **Date**: 2026-05-20

---

## Entities

### 1. `ExecutionSignal`

Composite input to the execution engine. Bundles the validated SMC signal with its pre-computed risk parameters.

```python
@dataclass
class ExecutionSignal:
    entry_signal: EntrySignal       # From src/engine/models.py (spec002)
    risk_calc: RiskCalculation      # From src/risk/models.py (spec003)
    signal_id: str                  # UUID — used for audit correlation
    received_at: datetime           # UTC timestamp when signal entered the engine
```

**Invariants**:
- `risk_calc.lot_size > 0.0` — caller must not pass a blocked zero-lot signal
- `entry_signal.direction != Direction.NONE`
- `signal_id` uniquely identifies this execution attempt across audit logs

**Relationships**: Contains `EntrySignal` (spec002) and `RiskCalculation` (spec003).

---

### 2. `OrderTicket`

Broker-assigned record returned after a successful `mt5.order_send()`. Engine-side snapshot for audit purposes.

```python
@dataclass
class OrderTicket:
    ticket_id: int                  # MT5 broker ticket number
    direction: Direction            # LONG or SHORT
    lot_size: float                 # Actual filled volume
    requested_price: float          # Price submitted in order request
    actual_fill_price: float        # Actual fill price from MT5 result (slippage-adjusted)
    sl_price: float
    tp_price: float                 # TP2 as primary exit
    open_time: datetime             # UTC open time from broker
    magic_number: int
```

**Relationships**: Created from `mt5.order_send()` result; referenced by `PositionState` and `TradeAuditEntry`.

---

### 3. `PositionState`

Engine's in-memory view of a single open position. Tracks derived state the broker does not store.

```python
@dataclass
class PositionState:
    ticket_id: int
    direction: Direction
    entry_price: float              # Original fill price at open
    current_sl: float               # Current SL (may differ from entry SL after trailing)
    tp1_price: float
    tp2_price: float
    lot_size: float                 # Current open volume (after partial close: lot_size - closed_lots)
    trailing_activated: bool        # True once trailing condition first triggered
    partial_close_done: bool        # True after TP1 partial close executed
    signal_id: str                  # Links back to ExecutionSignal for audit
    opened_at: datetime
```

**State Transitions**:
```
OPEN
  │
  ├── price reaches trailing threshold  →  trailing_activated = True; SL moves
  │                                         SL continues moving with price (unidirectional)
  │
  ├── price reaches TP1                 →  partial_close_done = True
  │                                         lot_size reduced; current_sl moved to entry_price
  │
  ├── price reaches TP2                 →  position fully closed; removed from dict
  │
  └── SL hit / external close           →  detected by reconciliation; removed from dict
```

**Invariants**:
- `current_sl` never moves against the trade direction
- `partial_close_done = True` implies `current_sl == entry_price`

---

### 4. `TradeAuditEntry`

Immutable record of a single order action. Appended to `logs/trades.json`.

```python
@dataclass
class TradeAuditEntry:
    audit_id: str                   # UUID for this entry
    timestamp_utc: str              # ISO-8601 UTC
    action_type: AuditAction        # See enum below
    signal_id: str                  # Links to ExecutionSignal (empty for position management events)
    ticket_id: Optional[int]        # MT5 broker ticket; None for pre-broker rejections
    direction: Optional[str]        # "LONG" / "SHORT" / None
    lot_size: Optional[float]
    requested_entry_price: Optional[float]
    actual_fill_price: Optional[float]
    sl_price: Optional[float]
    tp1_price: Optional[float]
    tp2_price: Optional[float]
    exit_price: Optional[float]     # Populated on PARTIAL_CLOSE, FULL_CLOSE
    realised_pnl: Optional[float]   # USD; populated on PARTIAL_CLOSE, FULL_CLOSE
    rejection_reason: Optional[str] # Populated on ORDER_REJECTED
    new_sl_price: Optional[float]   # Populated on TRAILING_STOP_UPDATED, BREAKEVEN_SET
    max_loss_usd: Optional[float]   # Populated on ORDER_PLACED — USD loss if SL is hit (CLAUDE.md §Risk First)
    entry_reason: Optional[str]     # Populated on ORDER_PLACED — set to EntrySignal.reason from src/engine/models.py (CLAUDE.md §Auditability)
    exit_reason: Optional[str]      # Populated on PARTIAL_CLOSE, FULL_CLOSE, POSITION_EXTERNALLY_CLOSED (CLAUDE.md §Auditability)
```

**`AuditAction` Enum**:
```python
class AuditAction(Enum):
    ORDER_PLACED         = "ORDER_PLACED"
    ORDER_REJECTED       = "ORDER_REJECTED"
    TRAILING_STOP_UPDATED = "TRAILING_STOP_UPDATED"
    BREAKEVEN_SET        = "BREAKEVEN_SET"
    PARTIAL_CLOSE        = "PARTIAL_CLOSE"
    FULL_CLOSE           = "FULL_CLOSE"
    SL_MODIFICATION_FAILED = "SL_MODIFICATION_FAILED"
    POSITION_EXTERNALLY_CLOSED = "POSITION_EXTERNALLY_CLOSED"
```

**Invariants** (FR-017):
- `timestamp_utc` always present
- `action_type` always present
- For `ORDER_PLACED`: `ticket_id`, `lot_size`, `actual_fill_price`, `sl_price`, `tp1_price`, `tp2_price`, `max_loss_usd`, `entry_reason` all non-None
- For `ORDER_REJECTED`: `rejection_reason` non-None
- For `PARTIAL_CLOSE` / `FULL_CLOSE`: `exit_price`, `realised_pnl`, `exit_reason` non-None
- For `POSITION_EXTERNALLY_CLOSED`: `exit_reason` non-None (value: `"SL hit"` or `"external close"`)

---

### 5. `KillSwitchState`

Binary flag controlling new order placement. Persisted to `logs/kill_switch.json`.

```python
@dataclass
class KillSwitchState:
    active: bool
    activated_at: Optional[datetime]    # UTC timestamp when activated
    activated_by: Optional[str]         # Free-text operator note
```

**File format** (`logs/kill_switch.json`):
```json
{
  "active": false,
  "activated_at": null,
  "activated_by": null
}
```

**Rules**:
- Read on every pre-flight check cycle (FR-014, FR-015)
- Written atomically (temp file + rename) to prevent corrupt reads
- Default state = `{"active": false}` (file absent = kill-switch inactive)

---

## Entity Relationships

```
ExecutionSignal
   ├── entry_signal: EntrySignal    (from spec002)
   └── risk_calc: RiskCalculation   (from spec003)
         │
         ▼
   [Pre-flight checks] ──── KillSwitchState (read)
         │                   PositionState dict (read — pyramiding check)
         │                   MT5 account_info (margin check)
         │                   MT5 symbol_info (min stop check)
         │
         ▼
   [OrderManager.place_order()] ──→ OrderTicket
         │
         ▼
   PositionState (created and stored in engine dict)
         │
         ├── [manage_positions()] → TRAILING_STOP_UPDATED → TradeAuditEntry
         │
         ├── [manage_positions()] → PARTIAL_CLOSE → TradeAuditEntry
         │                          BREAKEVEN_SET → TradeAuditEntry
         │
         └── [manage_positions()] → FULL_CLOSE / POSITION_EXTERNALLY_CLOSED → TradeAuditEntry

Every action → TradeAuditEntry appended to logs/trades.json
```

---

## Validation Rules

| Entity | Field | Rule |
|--------|-------|------|
| `ExecutionSignal` | `risk_calc.lot_size` | Must be > 0.0 (blocked signals must not enter engine) |
| `ExecutionSignal` | `entry_signal.direction` | Must not be `Direction.NONE` |
| `PositionState` | `current_sl` | LONG: sl < entry_price; SHORT: sl > entry_price |
| `PositionState` | `current_sl` after trailing | LONG: only increases; SHORT: only decreases |
| `TradeAuditEntry` | `realised_pnl` on close | Must be computed from actual fill price, not requested price |
| `KillSwitchState` | file absent | Treated as `active=False`; not an error |
