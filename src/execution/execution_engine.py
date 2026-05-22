"""ExecutionEngine — main orchestrator for order execution and position management."""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from src.broker.order_manager import OrderManager, OrderType
from src.execution.audit_logger import write_audit_entries, write_audit_entry
from src.execution.position_manager import manage_positions
from src.execution.models import (
    AuditAction,
    Direction,
    ExecutionSignal,
    PositionState,
    TradeAuditEntry,
)
from src.execution.preflight import run_preflight


class ExecutionEngine:
    """Terminal stage of the Shikra pipeline — places orders and manages open positions."""

    def __init__(
        self,
        order_manager: OrderManager,
        config: dict,
        kill_switch_path: Optional[Path] = None,
    ) -> None:
        self._order_manager = order_manager
        self._config = config
        self._kill_switch_path = kill_switch_path
        self._positions: dict[int, PositionState] = {}

    @property
    def open_positions(self) -> dict[int, PositionState]:
        """Read-only snapshot of currently tracked positions."""
        return dict(self._positions)

    def execute_signal(
        self,
        exec_signal: ExecutionSignal,
        day_start_equity: float,
        current_equity: float,
    ) -> TradeAuditEntry:
        """Run preflight → place order → build PositionState → write audit entry.

        Returns ORDER_PLACED on success, ORDER_REJECTED on any failure. Never raises.
        entry_reason populated from exec_signal.entry_signal.reason (CHK009 fix).
        """
        try:
            ok, reason = run_preflight(
                exec_signal,
                self._positions,
                day_start_equity,
                current_equity,
                self._config,
                self._kill_switch_path,
            )
            if not ok:
                return self._reject(exec_signal, reason)

            direction = exec_signal.entry_signal.direction
            order_type = OrderType.BUY if direction == Direction.LONG else OrderType.SELL

            trade = self._order_manager.place_order(
                order_type=order_type,
                volume=exec_signal.risk_calc.lot_size,
                stop_loss=exec_signal.risk_calc.sl_price,
                take_profit=exec_signal.risk_calc.tp2_price,
            )

            if trade.result != "success":
                return self._reject(exec_signal, trade.error_message or trade.result)

            pos = PositionState(
                ticket_id=trade.broker_ticket,
                direction=direction,
                entry_price=trade.entry_price,
                current_sl=exec_signal.risk_calc.sl_price,
                tp1_price=exec_signal.risk_calc.tp1_price,
                tp2_price=exec_signal.risk_calc.tp2_price,
                lot_size=exec_signal.risk_calc.lot_size,
                signal_id=exec_signal.signal_id,
                opened_at=datetime.utcnow(),
            )
            self._positions[trade.broker_ticket] = pos

            entry = TradeAuditEntry(
                audit_id=str(uuid.uuid4()),
                timestamp_utc=datetime.utcnow().isoformat(),
                action_type=AuditAction.ORDER_PLACED,
                signal_id=exec_signal.signal_id,
                ticket_id=trade.broker_ticket,
                direction=direction.value,
                lot_size=exec_signal.risk_calc.lot_size,
                requested_entry_price=trade.entry_price,
                actual_fill_price=trade.entry_price,
                sl_price=exec_signal.risk_calc.sl_price,
                tp1_price=exec_signal.risk_calc.tp1_price,
                tp2_price=exec_signal.risk_calc.tp2_price,
                max_loss_usd=trade.max_loss_usd,
                entry_reason=exec_signal.entry_signal.reason,  # CHK009 fix
            )
            write_audit_entry(entry)
            return entry

        except Exception as exc:
            logger.error(f"execute_signal unexpected error — {exc}")
            return self._reject(exec_signal, f"engine error: {exc}")

    def manage_open_positions(self, current_price: float) -> list[TradeAuditEntry]:
        """Bar-level position lifecycle — trail, partial close, TP2 close, reconcile.

        Kill-switch does NOT block this method — existing positions are managed
        normally even when new order placement is halted (US4-S2).
        Delegates to manage_positions(), flushes all audit entries, returns them.
        """
        updated, entries = manage_positions(self._positions, current_price, self._config)
        self._positions = updated
        if entries:
            write_audit_entries(entries)
        return entries

    def _reject(self, exec_signal: ExecutionSignal, reason: str) -> TradeAuditEntry:
        """Build and write an ORDER_REJECTED audit entry; never raises."""
        entry = TradeAuditEntry(
            audit_id=str(uuid.uuid4()),
            timestamp_utc=datetime.utcnow().isoformat(),
            action_type=AuditAction.ORDER_REJECTED,
            signal_id=exec_signal.signal_id,
            direction=exec_signal.entry_signal.direction.value,
            lot_size=exec_signal.risk_calc.lot_size,
            rejection_reason=reason,
        )
        write_audit_entry(entry)
        return entry
