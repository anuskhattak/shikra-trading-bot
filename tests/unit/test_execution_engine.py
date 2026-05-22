"""Unit tests for ExecutionEngine.execute_signal() — T015."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.broker.order_manager import OrderManager, OrderType, TradeOrder
from src.engine.models import Direction, EntrySignal
from src.execution.execution_engine import ExecutionEngine
from src.execution.models import AuditAction, ExecutionSignal, PositionState, TradeAuditEntry
from src.risk.models import RiskCalculation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry_signal(direction: Direction = Direction.LONG, reason: str = "BOS + FVG") -> EntrySignal:
    return EntrySignal(
        direction=direction,
        confidence=0.85,
        entry_zone_top=1900.0,
        entry_zone_bottom=1895.0,
        reason=reason,
    )


def _risk_calc(sl: float = 1880.0) -> RiskCalculation:
    return RiskCalculation(
        lot_size=0.05,
        sl_price=sl,
        tp1_price=1920.0,
        tp2_price=1940.0,
        sl_distance=abs(1897.5 - sl),
        risk_amount_usd=50.0,
        in_recovery=False,
        reason="valid",
    )


def _exec_signal(
    direction: Direction = Direction.LONG,
    sl: float = 1880.0,
    reason: str = "BOS + FVG",
    signal_id: str = "test-uuid-001",
) -> ExecutionSignal:
    return ExecutionSignal(
        entry_signal=_entry_signal(direction, reason),
        risk_calc=_risk_calc(sl),
        signal_id=signal_id,
        received_at=datetime.utcnow(),
    )


def _success_trade(ticket: int = 99001, price: float = 1900.0, max_loss: float = 100.0) -> TradeOrder:
    return TradeOrder(
        order_type="BUY",
        entry_price=price,
        stop_loss=1880.0,
        take_profit=1940.0,
        volume=0.05,
        magic_number=202605,
        timestamp=datetime.utcnow().isoformat(),
        result="success",
        broker_ticket=ticket,
        max_loss_usd=max_loss,
    )


def _failed_trade(error: str = "broker error") -> TradeOrder:
    return TradeOrder(
        order_type="BUY",
        entry_price=1900.0,
        stop_loss=1880.0,
        take_profit=1940.0,
        volume=0.05,
        magic_number=202605,
        timestamp=datetime.utcnow().isoformat(),
        result="failed",
        error_message=error,
    )


@pytest.fixture
def engine_with_mocks(tmp_path):
    """Return (ExecutionEngine, mock_order_manager, kill_switch_path)."""
    mgr = MagicMock(spec=OrderManager)
    config = {"risk": {"max_daily_drawdown_pct": 5.0}}
    ks_path = tmp_path / "kill_switch.json"  # absent = inactive
    eng = ExecutionEngine(order_manager=mgr, config=config, kill_switch_path=ks_path)
    return eng, mgr, ks_path


# ---------------------------------------------------------------------------
# T015 — Happy path: ORDER_PLACED
# ---------------------------------------------------------------------------

class TestExecuteSignalHappyPath:
    def test_order_placed_action_type(self, engine_with_mocks, monkeypatch):
        eng, mgr, _ = engine_with_mocks
        mgr.place_order.return_value = _success_trade(ticket=99001)
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)
        monkeypatch.setattr(
            "src.execution.execution_engine.run_preflight", lambda *a, **kw: (True, "")
        )

        result = eng.execute_signal(_exec_signal(), 10000.0, 10000.0)

        assert result.action_type == AuditAction.ORDER_PLACED

    def test_ticket_id_from_broker_response(self, engine_with_mocks, monkeypatch):
        eng, mgr, _ = engine_with_mocks
        mgr.place_order.return_value = _success_trade(ticket=88001)
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)
        monkeypatch.setattr(
            "src.execution.execution_engine.run_preflight", lambda *a, **kw: (True, "")
        )

        result = eng.execute_signal(_exec_signal(), 10000.0, 10000.0)

        assert result.ticket_id == 88001

    def test_signal_id_preserved_in_audit_entry(self, engine_with_mocks, monkeypatch):
        eng, mgr, _ = engine_with_mocks
        mgr.place_order.return_value = _success_trade()
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)
        monkeypatch.setattr(
            "src.execution.execution_engine.run_preflight", lambda *a, **kw: (True, "")
        )

        result = eng.execute_signal(_exec_signal(signal_id="my-signal-abc"), 10000.0, 10000.0)

        assert result.signal_id == "my-signal-abc"

    def test_entry_reason_from_entry_signal(self, engine_with_mocks, monkeypatch):
        """CHK009 fix — entry_reason must map to EntrySignal.reason."""
        eng, mgr, _ = engine_with_mocks
        mgr.place_order.return_value = _success_trade()
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)
        monkeypatch.setattr(
            "src.execution.execution_engine.run_preflight", lambda *a, **kw: (True, "")
        )

        result = eng.execute_signal(_exec_signal(reason="CHoCH + OB retest"), 10000.0, 10000.0)

        assert result.entry_reason == "CHoCH + OB retest"

    def test_max_loss_usd_from_trade_result(self, engine_with_mocks, monkeypatch):
        eng, mgr, _ = engine_with_mocks
        mgr.place_order.return_value = _success_trade(max_loss=75.0)
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)
        monkeypatch.setattr(
            "src.execution.execution_engine.run_preflight", lambda *a, **kw: (True, "")
        )

        result = eng.execute_signal(_exec_signal(), 10000.0, 10000.0)

        assert result.max_loss_usd == 75.0

    def test_position_added_to_dict(self, engine_with_mocks, monkeypatch):
        eng, mgr, _ = engine_with_mocks
        mgr.place_order.return_value = _success_trade(ticket=77001)
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)
        monkeypatch.setattr(
            "src.execution.execution_engine.run_preflight", lambda *a, **kw: (True, "")
        )

        eng.execute_signal(_exec_signal(), 10000.0, 10000.0)

        assert 77001 in eng.open_positions
        pos = eng.open_positions[77001]
        assert pos.direction == Direction.LONG
        assert pos.tp1_price == 1920.0
        assert pos.tp2_price == 1940.0

    def test_short_signal_calls_sell_order(self, engine_with_mocks, monkeypatch):
        eng, mgr, _ = engine_with_mocks
        sell_trade = TradeOrder(
            order_type="SELL", entry_price=1900.0, stop_loss=1920.0, take_profit=1860.0,
            volume=0.05, magic_number=202605, timestamp=datetime.utcnow().isoformat(),
            result="success", broker_ticket=55001, max_loss_usd=100.0,
        )
        mgr.place_order.return_value = sell_trade
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)
        monkeypatch.setattr(
            "src.execution.execution_engine.run_preflight", lambda *a, **kw: (True, "")
        )

        eng.execute_signal(_exec_signal(direction=Direction.SHORT, sl=1920.0), 10000.0, 10000.0)

        call_kwargs = mgr.place_order.call_args.kwargs
        assert call_kwargs["order_type"] == OrderType.SELL


# ---------------------------------------------------------------------------
# T015 — Rejection scenarios
# ---------------------------------------------------------------------------

class TestExecuteSignalRejections:
    def test_kill_switch_rejection_no_broker_call(self, engine_with_mocks, monkeypatch):
        """US4 Scenario 1 — kill-switch blocks; no order placed."""
        eng, mgr, ks_path = engine_with_mocks
        from src.execution.kill_switch import activate_kill_switch
        activate_kill_switch(path=ks_path)
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)

        result = eng.execute_signal(_exec_signal(), 10000.0, 10000.0)

        assert result.action_type == AuditAction.ORDER_REJECTED
        assert "kill-switch" in result.rejection_reason.lower()
        mgr.place_order.assert_not_called()

    def test_pyramiding_rejection_no_broker_call(self, engine_with_mocks, monkeypatch):
        """US1 — same-direction position blocks second entry without broker call."""
        eng, mgr, _ = engine_with_mocks
        eng._positions[12345] = PositionState(
            ticket_id=12345, direction=Direction.LONG, entry_price=1900.0,
            current_sl=1880.0, tp1_price=1920.0, tp2_price=1940.0, lot_size=0.05,
        )
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)

        result = eng.execute_signal(_exec_signal(Direction.LONG), 10000.0, 10000.0)

        assert result.action_type == AuditAction.ORDER_REJECTED
        assert "pyramiding" in result.rejection_reason.lower()
        mgr.place_order.assert_not_called()

    def test_drawdown_rejection(self, engine_with_mocks, monkeypatch):
        """US1 Scenario 2 — daily drawdown blocks order."""
        eng, mgr, _ = engine_with_mocks
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)
        monkeypatch.setattr("src.execution.preflight.check_margin_sufficiency", lambda l: (True, ""))
        monkeypatch.setattr("src.execution.preflight.check_minimum_stop_distance", lambda *a: (True, ""))

        result = eng.execute_signal(_exec_signal(), 10000.0, 9000.0)  # 10% drawdown

        assert result.action_type == AuditAction.ORDER_REJECTED
        assert "drawdown" in result.rejection_reason.lower()

    def test_broker_failure_returns_rejected(self, engine_with_mocks, monkeypatch):
        """US1 Scenario 5 — broker connection failure → ORDER_REJECTED, no partial state."""
        eng, mgr, _ = engine_with_mocks
        mgr.place_order.return_value = _failed_trade("broker timeout")
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)
        monkeypatch.setattr(
            "src.execution.execution_engine.run_preflight", lambda *a, **kw: (True, "")
        )

        result = eng.execute_signal(_exec_signal(), 10000.0, 10000.0)

        assert result.action_type == AuditAction.ORDER_REJECTED
        assert "broker timeout" in result.rejection_reason

    def test_broker_failure_no_position_in_dict(self, engine_with_mocks, monkeypatch):
        eng, mgr, _ = engine_with_mocks
        mgr.place_order.return_value = _failed_trade("error")
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)
        monkeypatch.setattr(
            "src.execution.execution_engine.run_preflight", lambda *a, **kw: (True, "")
        )

        eng.execute_signal(_exec_signal(), 10000.0, 10000.0)

        assert len(eng.open_positions) == 0

    def test_rejection_contains_signal_id(self, engine_with_mocks, monkeypatch):
        eng, mgr, ks_path = engine_with_mocks
        from src.execution.kill_switch import activate_kill_switch
        activate_kill_switch(path=ks_path)
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)

        result = eng.execute_signal(
            _exec_signal(signal_id="sig-xyz"), 10000.0, 10000.0
        )

        assert result.signal_id == "sig-xyz"


# ---------------------------------------------------------------------------
# T015 — open_positions property
# ---------------------------------------------------------------------------

class TestOpenPositionsProperty:
    def test_empty_at_init(self, engine_with_mocks):
        eng, _, _ = engine_with_mocks
        assert eng.open_positions == {}

    def test_returns_copy_not_reference(self, engine_with_mocks, monkeypatch):
        eng, mgr, _ = engine_with_mocks
        mgr.place_order.return_value = _success_trade(ticket=55001)
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)
        monkeypatch.setattr(
            "src.execution.execution_engine.run_preflight", lambda *a, **kw: (True, "")
        )
        eng.execute_signal(_exec_signal(), 10000.0, 10000.0)

        snapshot = eng.open_positions
        snapshot[99999] = MagicMock()  # mutate the copy

        assert 99999 not in eng.open_positions  # internal dict unchanged

    def test_multiple_positions_tracked(self, engine_with_mocks, monkeypatch):
        eng, mgr, _ = engine_with_mocks
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)
        monkeypatch.setattr(
            "src.execution.execution_engine.run_preflight", lambda *a, **kw: (True, "")
        )
        mgr.place_order.side_effect = [
            _success_trade(ticket=1001),
            _success_trade(ticket=1002),
        ]

        eng.execute_signal(_exec_signal(Direction.LONG), 10000.0, 10000.0)
        eng.execute_signal(_exec_signal(Direction.SHORT, sl=1920.0), 10000.0, 10000.0)

        assert 1001 in eng.open_positions
        assert 1002 in eng.open_positions


# ---------------------------------------------------------------------------
# T024 — manage_open_positions()
# ---------------------------------------------------------------------------

class TestManageOpenPositions:
    """US4-S2: kill-switch allows position management but blocks new execute_signal() calls."""

    def test_empty_positions_returns_empty_list(self, engine_with_mocks, monkeypatch):
        eng, _, _ = engine_with_mocks
        monkeypatch.setattr(
            "src.execution.execution_engine.manage_positions",
            lambda positions, price, cfg: ({}, []),
        )
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entries", lambda e: None)

        result = eng.manage_open_positions(current_price=1900.0)

        assert result == []

    def test_returns_audit_entries_from_manage_positions(self, engine_with_mocks, monkeypatch):
        """End-to-end: manage_positions returns entries → manage_open_positions relays them."""
        eng, _, _ = engine_with_mocks
        fake_entry = TradeAuditEntry(
            audit_id="fake-001",
            timestamp_utc="2026-05-22T10:00:00",
            action_type=AuditAction.TRAILING_STOP_UPDATED,
            signal_id="sig-trail-001",
            ticket_id=99001,
        )
        monkeypatch.setattr(
            "src.execution.execution_engine.manage_positions",
            lambda positions, price, cfg: (positions, [fake_entry]),
        )
        written: list = []
        monkeypatch.setattr(
            "src.execution.execution_engine.write_audit_entries",
            lambda entries: written.extend(entries),
        )

        result = eng.manage_open_positions(current_price=1900.0)

        assert len(result) == 1
        assert result[0].action_type == AuditAction.TRAILING_STOP_UPDATED
        assert len(written) == 1

    def test_positions_dict_updated_after_manage(self, engine_with_mocks, monkeypatch):
        """Internal _positions dict is replaced with the updated dict from manage_positions."""
        eng, _, _ = engine_with_mocks
        remaining = {
            77001: PositionState(
                ticket_id=77001, direction=Direction.LONG, entry_price=1900.0,
                current_sl=1880.0, tp1_price=1920.0, tp2_price=1940.0, lot_size=0.05,
            )
        }
        monkeypatch.setattr(
            "src.execution.execution_engine.manage_positions",
            lambda positions, price, cfg: (remaining, []),
        )
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entries", lambda e: None)

        eng.manage_open_positions(current_price=1900.0)

        assert 77001 in eng.open_positions

    def test_kill_switch_blocks_execute_signal_but_not_manage(
        self, engine_with_mocks, monkeypatch
    ):
        """US4-S2: kill-switch active → execute_signal() returns ORDER_REJECTED,
        but manage_open_positions() still delegates to manage_positions normally."""
        eng, mgr, ks_path = engine_with_mocks
        from src.execution.kill_switch import activate_kill_switch
        activate_kill_switch(path=ks_path)

        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)

        # execute_signal must be rejected
        rejection = eng.execute_signal(_exec_signal(), 10000.0, 10000.0)
        assert rejection.action_type == AuditAction.ORDER_REJECTED
        mgr.place_order.assert_not_called()

        # manage_open_positions must still run
        manage_called = []
        monkeypatch.setattr(
            "src.execution.execution_engine.manage_positions",
            lambda positions, price, cfg: manage_called.append(True) or ({}, []),
        )
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entries", lambda e: None)

        eng.manage_open_positions(current_price=1900.0)

        assert manage_called, "manage_positions must be called even when kill-switch is active"

    def test_write_audit_entries_not_called_for_empty_entries(
        self, engine_with_mocks, monkeypatch
    ):
        eng, _, _ = engine_with_mocks
        monkeypatch.setattr(
            "src.execution.execution_engine.manage_positions",
            lambda positions, price, cfg: ({}, []),
        )
        write_called = []
        monkeypatch.setattr(
            "src.execution.execution_engine.write_audit_entries",
            lambda e: write_called.append(e),
        )

        eng.manage_open_positions(current_price=1900.0)

        assert not write_called, "write_audit_entries must not be called when entries list is empty"
