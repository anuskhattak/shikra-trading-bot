"""Execution Engine — order placement, position management, kill-switch, audit trail."""
from src.execution.audit_logger import write_audit_entries, write_audit_entry
from src.execution.kill_switch import (
    activate_kill_switch,
    deactivate_kill_switch,
    is_kill_switch_active,
)
from src.execution.models import (
    AuditAction,
    ExecutionSignal,
    KillSwitchState,
    OrderTicket,
    PositionState,
    TradeAuditEntry,
)

__all__ = [
    "ExecutionEngine",
    "ExecutionSignal",
    "PositionState",
    "TradeAuditEntry",
    "AuditAction",
    "KillSwitchState",
    "OrderTicket",
    "activate_kill_switch",
    "deactivate_kill_switch",
    "is_kill_switch_active",
    "write_audit_entry",
    "write_audit_entries",
]


def __getattr__(name: str):
    # Lazy import for ExecutionEngine — avoids circular import with src.broker.order_manager
    # (order_manager imports audit_logger; __init__ importing ExecutionEngine would close the cycle)
    if name == "ExecutionEngine":
        from src.execution.execution_engine import ExecutionEngine
        return ExecutionEngine
    raise AttributeError(f"module 'src.execution' has no attribute {name!r}")
