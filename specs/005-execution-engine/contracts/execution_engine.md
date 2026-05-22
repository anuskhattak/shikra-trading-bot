# API Contract: Execution Engine (spec005)

**Module**: `src/execution/`  
**Branch**: `005-execution-engine` | **Date**: 2026-05-20

---

## Module: `src/execution/models.py`

All execution engine data types. No MT5 imports.

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from src.engine.models import Direction, EntrySignal
from src.risk.models import RiskCalculation


class AuditAction(Enum):
    ORDER_PLACED               = "ORDER_PLACED"
    ORDER_REJECTED             = "ORDER_REJECTED"
    TRAILING_STOP_UPDATED      = "TRAILING_STOP_UPDATED"
    BREAKEVEN_SET              = "BREAKEVEN_SET"
    PARTIAL_CLOSE              = "PARTIAL_CLOSE"
    FULL_CLOSE                 = "FULL_CLOSE"
    SL_MODIFICATION_FAILED     = "SL_MODIFICATION_FAILED"
    POSITION_EXTERNALLY_CLOSED = "POSITION_EXTERNALLY_CLOSED"


@dataclass
class ExecutionSignal:
    entry_signal: EntrySignal
    risk_calc: RiskCalculation
    signal_id: str               # UUID
    received_at: datetime        # UTC


@dataclass
class PositionState:
    ticket_id: int
    direction: Direction
    entry_price: float
    current_sl: float
    tp1_price: float
    tp2_price: float
    lot_size: float
    trailing_activated: bool = False
    partial_close_done: bool = False
    signal_id: str = ""
    opened_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TradeAuditEntry:
    audit_id: str
    timestamp_utc: str
    action_type: AuditAction
    signal_id: str
    ticket_id: Optional[int] = None
    direction: Optional[str] = None
    lot_size: Optional[float] = None
    requested_entry_price: Optional[float] = None
    actual_fill_price: Optional[float] = None
    sl_price: Optional[float] = None
    tp1_price: Optional[float] = None
    tp2_price: Optional[float] = None
    exit_price: Optional[float] = None
    realised_pnl: Optional[float] = None
    rejection_reason: Optional[str] = None
    new_sl_price: Optional[float] = None
    max_loss_usd: Optional[float] = None      # ORDER_PLACED: USD loss if SL hit (CLAUDE.md §Risk First)
    entry_reason: Optional[str] = None        # ORDER_PLACED: set to exec_signal.entry_signal.reason (src/engine/models.py — CLAUDE.md §Auditability)
    exit_reason: Optional[str] = None         # PARTIAL_CLOSE / FULL_CLOSE / POSITION_EXTERNALLY_CLOSED


@dataclass
class KillSwitchState:
    active: bool = False
    activated_at: Optional[datetime] = None
    activated_by: Optional[str] = None
```

---

## Module: `src/execution/preflight.py`

Pre-flight validation checks. All checks are pure functions or read-only MT5 queries. Returns `(passed: bool, reason: str)`.

```python
def check_kill_switch(kill_switch_path: Path) -> tuple[bool, str]:
    """
    Read kill_switch.json and return (False, "kill-switch active") when active.
    Returns (True, "") when inactive or file absent.
    File absent → treated as inactive (safe default).
    Raises no exceptions — file errors → assume inactive, log warning.
    """
    ...

def check_existing_position(
    positions: dict[int, PositionState],
    direction: Direction,
) -> tuple[bool, str]:
    """
    Return (False, "existing {direction} position open — pyramiding prevented")
    if any PositionState in positions matches direction.
    Returns (True, "") when no conflict.
    """
    ...

def check_daily_drawdown(
    day_start_equity: float,
    current_equity: float,
    max_pct: float,
) -> tuple[bool, str]:
    """
    Delegate to src.risk.drawdown_guard.check_drawdown().
    check_drawdown() returns TradeAllowedResult(allowed, reason) — unpack before returning:
        result = check_drawdown(day_start_equity, current_equity, max_pct)
        return result.allowed, result.reason
    Returns (False, reason) when drawdown >= max_pct; (True, "") otherwise.
    """
    ...

def check_margin_sufficiency(lot_size: float) -> tuple[bool, str]:
    """
    Call mt5.order_check() with the proposed order parameters.
    Returns (False, "insufficient margin") when mt5.order_check fails margin validation.
    Returns (True, "") on sufficient margin.
    """
    ...

def check_minimum_stop_distance(
    direction: Direction,
    entry_price: float,
    sl_price: float,
) -> tuple[bool, str]:
    """
    Query mt5.symbol_info("XAUUSD").trade_stops_level to get minimum stop distance in points.
    Convert to price units: min_distance = stops_level * symbol_info.point
    Return (False, "SL distance below minimum") when abs(entry_price - sl_price) < min_distance.
    """
    ...

def run_preflight(
    exec_signal: ExecutionSignal,
    positions: dict[int, PositionState],
    day_start_equity: float,
    current_equity: float,
    config: dict,
    kill_switch_path: Path,
) -> tuple[bool, str]:
    """
    Run all checks in order (D-006):
      1. kill-switch
      2. pyramiding
      3. daily drawdown
      4. margin sufficiency
      5. minimum stop distance
    Short-circuit on first False. Return (True, "") if all pass.
    """
    ...
```

---

## Module: `src/execution/position_manager.py`

Position lifecycle management — trailing stop, partial close, stale detection. No direct audit logging; returns `list[TradeAuditEntry]`.

```python
def evaluate_trailing_stop(
    position: PositionState,
    current_price: float,
    config: dict,
) -> tuple[PositionState, Optional[TradeAuditEntry]]:
    """
    Trailing stop logic (FR-008, FR-009, FR-010).
    LONG:  trailing activates when current_price >= entry_price + trailing_activation_distance.
           new_sl = current_price - trailing_distance. Only applied when new_sl > current_sl.
    SHORT: symmetric.
    Returns (updated_state, audit_entry) or (unchanged_state, None) if no update.
    Does NOT call MT5 — returns the desired new SL; caller applies via modify_sl().
    """
    ...

def apply_partial_close(
    position: PositionState,
    config: dict,
    order_manager,      # src.broker.order_manager.OrderManager instance
) -> tuple[PositionState, list[TradeAuditEntry]]:
    """
    Execute partial close at TP1 (FR-011, FR-012).
    Steps:
      1. Calculate close_lots = round(position.lot_size * config["partial_close_ratio"], 2)
      2. Send counter-direction order via order_manager with position=ticket_id
      3. On success: update position.lot_size, set partial_close_done=True
      4. Move remaining SL to entry_price (BREAKEVEN_SET)
    Returns (updated_state, [PARTIAL_CLOSE_entry, BREAKEVEN_SET_entry]).
    On broker failure: returns (unchanged_state, [PARTIAL_CLOSE failure entry]).
    """
    ...

def reconcile_positions(
    engine_positions: dict[int, PositionState],
) -> tuple[dict[int, PositionState], list[TradeAuditEntry]]:
    """
    Detect externally closed positions (FR-013, edge case).
    Calls mt5.positions_get(symbol="XAUUSD"); tickets not in broker response are purged.
    Returns (cleaned_dict, [POSITION_EXTERNALLY_CLOSED entries]).
    """
    ...

def manage_positions(
    engine_positions: dict[int, PositionState],
    current_prices: dict[str, float],   # {"XAUUSD": ask_or_bid}
    config: dict,
    order_manager,
) -> tuple[dict[int, PositionState], list[TradeAuditEntry]]:
    """
    Main position management entry point called on each H1 bar.
    Steps per open position:
      1. reconcile_positions() — prune externally closed
      2. check TP2 hit → full close
      3. check TP1 hit and not partial_close_done → apply_partial_close()
      4. evaluate_trailing_stop() → if new SL: modify via MT5 SLTP action
    Returns (updated_positions_dict, all_audit_entries).
    """
    ...
```

---

## Module: `src/execution/audit_logger.py`

Structured JSON audit logging. Thread-safe append to `logs/trades.json`.

```python
AUDIT_LOG = Path("logs/trades.json")

def write_audit_entry(entry: TradeAuditEntry) -> None:
    """
    Append TradeAuditEntry to logs/trades.json atomically.
    Uses threading.Lock() shared with src.broker.order_manager (same log file).
    On write failure: logs to stderr but does NOT raise (FR-018).
    """
    ...

def write_audit_entries(entries: list[TradeAuditEntry]) -> None:
    """Batch version — acquires lock once for all entries."""
    ...
```

---

## Module: `src/execution/execution_engine.py`

Main orchestrator. Single public entry point for order execution.

```python
class ExecutionEngine:
    """
    Orchestrates pre-flight → order placement → position tracking → audit logging.

    Caller contract:
      - Call execute_signal() on each new validated ExecutionSignal.
      - Call manage_open_positions() on each H1 bar close.
      - Never pass ExecutionSignal with risk_calc.lot_size == 0.0.
    """

    def __init__(
        self,
        order_manager,          # src.broker.order_manager.OrderManager
        config: dict,
        kill_switch_path: Path = Path("logs/kill_switch.json"),
    ) -> None: ...

    def execute_signal(
        self,
        exec_signal: ExecutionSignal,
        day_start_equity: float,
        current_equity: float,
    ) -> TradeAuditEntry:
        """
        Full execution flow:
          1. run_preflight() — returns ORDER_REJECTED entry on failure
          2. order_manager.place_order() — maps to MT5 BUY/SELL
          3. Create PositionState and store in self._positions
          4. Write ORDER_PLACED audit entry
          5. Return TradeAuditEntry

        Never raises. All failures produce an ORDER_REJECTED audit entry.
        """
        ...

    def manage_open_positions(
        self,
        current_prices: dict[str, float],
    ) -> list[TradeAuditEntry]:
        """
        Called on each H1 bar. Delegates to manage_positions().
        Writes all returned audit entries to audit log.
        Returns list of TradeAuditEntry generated this bar.
        """
        ...

    @property
    def open_positions(self) -> dict[int, PositionState]:
        """Read-only view of current position dict (for monitoring/tests)."""
        ...
```

---

## Module: `src/execution/kill_switch.py`

Operator-facing helpers for kill-switch management.

```python
def activate_kill_switch(
    path: Path = Path("logs/kill_switch.json"),
    reason: str = "",
) -> None:
    """Write kill_switch.json with active=True atomically (temp file + rename)."""
    ...

def deactivate_kill_switch(
    path: Path = Path("logs/kill_switch.json"),
) -> None:
    """Write kill_switch.json with active=False atomically."""
    ...

def is_kill_switch_active(
    path: Path = Path("logs/kill_switch.json"),
) -> bool:
    """Read current kill-switch state. Returns False if file absent or unreadable."""
    ...
```

---

## Module: `src/execution/__init__.py`

Public exports:

```python
from src.execution.execution_engine import ExecutionEngine
from src.execution.kill_switch import activate_kill_switch, deactivate_kill_switch, is_kill_switch_active
from src.execution.models import (
    AuditAction,
    ExecutionSignal,
    KillSwitchState,
    PositionState,
    TradeAuditEntry,
)
```

---

## Config Schema (additions to `config.yaml`)

```yaml
execution:
  trailing:
    activation_distance: 30.0       # Price units above/below entry to activate trailing
    trailing_distance: 20.0         # Price units to keep SL behind current price
  partial_close:
    tp1_close_ratio: 0.5            # Fraction of position to close at TP1
  magic_number: 20250519
  slippage_points: 5
  kill_switch_path: "logs/kill_switch.json"
  audit_log_path: "logs/trades.json"
```

---

## Error Handling Contract

| Scenario | Behaviour |
|----------|-----------|
| Pre-flight check fails | `ORDER_REJECTED` audit entry written; no broker call |
| Broker `order_send` timeout | `ORDER_REJECTED` audit entry with `rejection_reason="broker timeout"`; engine halts further orders until connection confirmed |
| Partial close broker failure | Full position remains; `PARTIAL_CLOSE` audit entry with failure flag; trailing stop continues on full lot |
| SL modification failure | Retry once; on second failure: `SL_MODIFICATION_FAILED` audit entry; alert raised |
| Audit log write fails | Error to stderr; trade action proceeds (FR-018) |
| Position externally closed | `POSITION_EXTERNALLY_CLOSED` audit entry; removed from engine dict |
