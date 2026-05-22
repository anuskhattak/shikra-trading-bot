"""Execution engine data models — all entities, enums, and dataclasses.

Zero MT5 imports. Every other execution module depends on these definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from src.engine.models import Direction, EntrySignal
from src.risk.models import RiskCalculation


class AuditAction(Enum):
    """Every action type the execution engine can produce an audit entry for."""

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
    """Composite input to the execution engine.

    Bundles a validated SMC EntrySignal with its pre-computed RiskCalculation.
    Caller invariants (must be enforced before constructing):
      - risk_calc.lot_size > 0.0  — blocked signals must never enter the engine
      - entry_signal.direction != Direction.NONE
      - signal_id is a unique UUID across audit logs
    """

    entry_signal: EntrySignal
    risk_calc: RiskCalculation
    signal_id: str       # UUID — audit correlation key
    received_at: datetime  # UTC timestamp when signal entered the engine


@dataclass
class OrderTicket:
    """Broker-assigned record returned after a successful mt5.order_send().

    Engine-side snapshot for audit purposes; not persisted beyond the session.
    """

    ticket_id: int
    direction: Direction
    lot_size: float
    requested_price: float
    actual_fill_price: float   # Slippage-adjusted fill from MT5 result
    sl_price: float
    tp_price: float            # TP2 used as the primary take-profit level
    open_time: datetime        # UTC open time from broker
    magic_number: int


@dataclass
class PositionState:
    """Engine's in-memory view of one open position.

    Tracks derived state the broker does not store (trailing_activated,
    partial_close_done). Lost on process restart — known limitation (ADR-0002).

    Invariants:
      - LONG:  current_sl < entry_price; after trailing only increases
      - SHORT: current_sl > entry_price; after trailing only decreases
      - partial_close_done=True implies current_sl == entry_price (breakeven)
    """

    ticket_id: int
    direction: Direction
    entry_price: float
    current_sl: float
    tp1_price: float
    tp2_price: float
    lot_size: float                  # Reduced after partial close
    trailing_activated: bool = False
    partial_close_done: bool = False
    signal_id: str = ""              # Links back to ExecutionSignal for audit
    opened_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TradeAuditEntry:
    """Immutable record of a single order action appended to logs/trades.json.

    Mandatory fields (always non-None):
      - audit_id, timestamp_utc, action_type, signal_id

    Field population rules per action_type (FR-017):
      - ORDER_PLACED:               ticket_id, lot_size, actual_fill_price, sl_price,
                                    tp1_price, tp2_price, max_loss_usd, entry_reason
      - ORDER_REJECTED:             rejection_reason
      - PARTIAL_CLOSE / FULL_CLOSE: exit_price, realised_pnl, exit_reason
      - POSITION_EXTERNALLY_CLOSED: exit_reason ("SL hit" or "external close")
      - TRAILING_STOP_UPDATED /
        BREAKEVEN_SET:              new_sl_price
    """

    audit_id: str
    timestamp_utc: str            # ISO-8601 UTC string
    action_type: AuditAction
    signal_id: str                # Empty string for position management events
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
    max_loss_usd: Optional[float] = None   # USD loss if SL is hit (CLAUDE.md §Risk First)
    entry_reason: Optional[str] = None     # EntrySignal.reason (CLAUDE.md §Auditability)
    exit_reason: Optional[str] = None      # Populated on close actions


@dataclass
class KillSwitchState:
    """Binary halt flag persisted to logs/kill_switch.json.

    File absent = active=False (safe default — never blocks on missing file).
    Written atomically via temp-file + rename to prevent corrupt reads.
    """

    active: bool = False
    activated_at: Optional[datetime] = None  # UTC timestamp when activated
    activated_by: Optional[str] = None       # Free-text operator note
