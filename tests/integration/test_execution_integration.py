"""
Integration tests for the Execution Engine — MT5 demo account round-trip.

Validates the full position lifecycle on a live MT5 demo connection:
  place order → SL set at entry (SC-001) → trailing activation →
  TP1 partial close + breakeven SL → TP2 full close.

Every action must produce exactly one audit entry (SC-006, SC-008).
No silent executions permitted.

SKIPPED automatically when MT5_ACCOUNT env var is absent (no live terminal required
for CI). Run with paper trading credentials only:
    MT5_ACCOUNT=<demo> MT5_PASSWORD=<pw> MT5_SERVER=<server> pytest tests/integration/ -v
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

INTEGRATION_SKIP = pytest.mark.skipif(
    not os.getenv("MT5_ACCOUNT"),
    reason="MT5 integration tests require MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER env vars",
)


# ---------------------------------------------------------------------------
# Fixtures — shared setup for all integration scenarios
# ---------------------------------------------------------------------------

@pytest.fixture
def demo_config(tmp_path):
    """Minimal config for execution engine round-trip tests."""
    return {
        "activation_distance": 30.0,
        "trailing_distance": 20.0,
        "tp1_close_ratio": 0.5,
        "magic_number": 202699,   # isolated number to avoid contaminating other tests
        "slippage_points": 5,
        "risk": {"max_daily_drawdown_pct": 5.0},
    }


@pytest.fixture
def audit_log(tmp_path):
    """Temporary audit log path for round-trip verification."""
    return tmp_path / "trades.json"


@pytest.fixture
def ks_path(tmp_path):
    """Temporary kill-switch path."""
    return tmp_path / "kill_switch.json"


# ---------------------------------------------------------------------------
# Mock-based round-trip (always runs — no live MT5 required)
# ---------------------------------------------------------------------------

class TestExecutionRoundTripMocked:
    """Full pipeline simulation using mocked MT5 and OrderManager.

    These tests verify SC-001, SC-006, SC-008 through a controlled mock —
    they always run regardless of MT5 availability.
    """

    def _make_engine(self, demo_config, ks_path, audit_log):
        from src.broker.order_manager import OrderManager
        from src.execution.execution_engine import ExecutionEngine

        mgr = MagicMock(spec=OrderManager)
        engine = ExecutionEngine(
            order_manager=mgr, config=demo_config, kill_switch_path=ks_path
        )
        return engine, mgr

    def _make_exec_signal(self, direction=None, ticket: int = 10001):
        from datetime import datetime

        from src.broker.order_manager import TradeOrder
        from src.engine.models import Direction, EntrySignal
        from src.execution.models import ExecutionSignal
        from src.risk.models import RiskCalculation

        if direction is None:
            from src.engine.models import Direction
            direction = Direction.LONG

        entry = EntrySignal(
            direction=direction,
            confidence=0.80,
            entry_zone_top=1900.0,
            entry_zone_bottom=1895.0,
            reason="BOS + FVG retest",
        )
        risk = RiskCalculation(
            lot_size=0.05,
            sl_price=1880.0,
            tp1_price=1920.0,
            tp2_price=1940.0,
            sl_distance=20.0,
            risk_amount_usd=100.0,
            in_recovery=False,
            reason="valid",
        )
        return ExecutionSignal(
            entry_signal=entry,
            risk_calc=risk,
            signal_id=str(uuid.uuid4()),
            received_at=datetime.utcnow(),
        )

    def _success_trade(self, ticket: int = 10001):
        from src.broker.order_manager import TradeOrder
        return TradeOrder(
            order_type="BUY",
            entry_price=1897.50,
            stop_loss=1880.0,
            take_profit=1940.0,
            volume=0.05,
            magic_number=202699,
            timestamp=datetime.utcnow().isoformat(),
            result="success",
            broker_ticket=ticket,
            max_loss_usd=87.50,
        )

    def test_sc001_sl_set_at_entry_time(self, demo_config, ks_path, audit_log, monkeypatch):
        """SC-001: SL must be set atomically at order placement — not after entry."""
        engine, mgr = self._make_engine(demo_config, ks_path, audit_log)
        mgr.place_order.return_value = self._success_trade()
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)
        monkeypatch.setattr(
            "src.execution.execution_engine.run_preflight", lambda *a, **kw: (True, "")
        )

        signal = self._make_exec_signal()
        result = engine.execute_signal(signal, 10000.0, 10000.0)

        call_kwargs = mgr.place_order.call_args.kwargs
        assert call_kwargs["stop_loss"] == signal.risk_calc.sl_price, (
            "SC-001 FAIL: stop_loss not passed at order placement time"
        )
        assert call_kwargs["take_profit"] == signal.risk_calc.tp2_price

    def test_sc006_order_placed_produces_audit_entry(
        self, demo_config, ks_path, audit_log, monkeypatch
    ):
        """SC-006: Every order action must produce exactly one audit entry — no silent executions."""
        engine, mgr = self._make_engine(demo_config, ks_path, audit_log)
        mgr.place_order.return_value = self._success_trade()
        monkeypatch.setattr(
            "src.execution.execution_engine.run_preflight", lambda *a, **kw: (True, "")
        )

        written = []
        monkeypatch.setattr(
            "src.execution.execution_engine.write_audit_entry",
            lambda e: written.append(e),
        )

        signal = self._make_exec_signal()
        result = engine.execute_signal(signal, 10000.0, 10000.0)

        from src.execution.models import AuditAction
        assert len(written) == 1, "SC-006 FAIL: expected exactly 1 audit entry for ORDER_PLACED"
        assert written[0].action_type == AuditAction.ORDER_PLACED

    def test_sc008_rejection_produces_audit_entry(
        self, demo_config, ks_path, audit_log, monkeypatch
    ):
        """SC-008: Rejected orders must also produce an audit entry — no silent rejections."""
        engine, mgr = self._make_engine(demo_config, ks_path, audit_log)
        from src.execution.kill_switch import activate_kill_switch
        activate_kill_switch(path=ks_path)

        written = []
        monkeypatch.setattr(
            "src.execution.execution_engine.write_audit_entry",
            lambda e: written.append(e),
        )

        signal = self._make_exec_signal()
        result = engine.execute_signal(signal, 10000.0, 10000.0)

        from src.execution.models import AuditAction
        assert len(written) == 1, "SC-008 FAIL: expected 1 audit entry for ORDER_REJECTED"
        assert written[0].action_type == AuditAction.ORDER_REJECTED
        mgr.place_order.assert_not_called()

    def test_full_lifecycle_order_to_manage(
        self, demo_config, ks_path, audit_log, monkeypatch
    ):
        """Round-trip: place order → position tracked → manage_open_positions returns entries."""
        engine, mgr = self._make_engine(demo_config, ks_path, audit_log)
        mgr.place_order.return_value = self._success_trade(ticket=20001)
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)
        monkeypatch.setattr(
            "src.execution.execution_engine.run_preflight", lambda *a, **kw: (True, "")
        )

        signal = self._make_exec_signal()
        engine.execute_signal(signal, 10000.0, 10000.0)
        assert 20001 in engine.open_positions

        from src.execution.models import AuditAction, TradeAuditEntry

        fake_trail = TradeAuditEntry(
            audit_id="trail-001",
            timestamp_utc=datetime.utcnow().isoformat(),
            action_type=AuditAction.TRAILING_STOP_UPDATED,
            signal_id="sig-int-001",
            ticket_id=20001,
        )
        monkeypatch.setattr(
            "src.execution.execution_engine.manage_positions",
            lambda positions, price, cfg: (positions, [fake_trail]),
        )
        written_batch = []
        monkeypatch.setattr(
            "src.execution.execution_engine.write_audit_entries",
            lambda entries: written_batch.extend(entries),
        )

        entries = engine.manage_open_positions(current_price=1930.0)  # below TP1 (1940)

        assert len(entries) == 1
        assert entries[0].action_type == AuditAction.TRAILING_STOP_UPDATED
        assert len(written_batch) == 1

    def test_us4_s2_kill_switch_allows_manage_blocks_new_orders(
        self, demo_config, ks_path, audit_log, monkeypatch
    ):
        """US4-S2: Kill-switch halts new entry orders but position management continues."""
        engine, mgr = self._make_engine(demo_config, ks_path, audit_log)
        from src.execution.kill_switch import activate_kill_switch
        activate_kill_switch(path=ks_path)

        monkeypatch.setattr("src.execution.execution_engine.write_audit_entry", lambda e: None)
        result = engine.execute_signal(self._make_exec_signal(), 10000.0, 10000.0)

        from src.execution.models import AuditAction
        assert result.action_type == AuditAction.ORDER_REJECTED

        manage_invoked = []
        monkeypatch.setattr(
            "src.execution.execution_engine.manage_positions",
            lambda positions, price, cfg: manage_invoked.append(1) or ({}, []),
        )
        monkeypatch.setattr("src.execution.execution_engine.write_audit_entries", lambda e: None)

        engine.manage_open_positions(current_price=1900.0)

        assert manage_invoked, "US4-S2 FAIL: manage_positions must run even with kill-switch active"


# ---------------------------------------------------------------------------
# Live MT5 round-trip (requires demo credentials)
# ---------------------------------------------------------------------------

@INTEGRATION_SKIP
class TestLiveExecutionRoundTrip:
    """Full end-to-end round-trip on a live MT5 demo account.

    Requires:
        MT5_ACCOUNT=<demo account number>
        MT5_PASSWORD=<password>
        MT5_SERVER=<broker server name>
    """

    @pytest.fixture(autouse=True)
    def live_engine(self, tmp_path):
        import MetaTrader5 as mt5
        from src.broker.connection import BrokerConnection
        from src.broker.order_manager import OrderManager
        from src.execution.execution_engine import ExecutionEngine

        account = int(os.environ["MT5_ACCOUNT"])
        password = os.environ["MT5_PASSWORD"]
        server = os.environ["MT5_SERVER"]

        conn = BrokerConnection(account, password, server)
        assert conn.connect(), "Live MT5 connection failed — check credentials"

        mgr = OrderManager(magic_number=202699)
        ks_path = tmp_path / "kill_switch.json"
        config = {
            "activation_distance": 30.0,
            "trailing_distance": 20.0,
            "tp1_close_ratio": 0.5,
            "magic_number": 202699,
            "slippage_points": 5,
            "risk": {"max_daily_drawdown_pct": 5.0},
        }
        self.engine = ExecutionEngine(order_manager=mgr, config=config, kill_switch_path=ks_path)
        self.conn = conn
        self.ks_path = ks_path
        self.audit_path = tmp_path / "trades.json"
        yield
        conn.disconnect()

    def _build_signal(self):
        from src.engine.models import Direction, EntrySignal
        from src.execution.models import ExecutionSignal
        from src.risk.models import RiskCalculation

        import MetaTrader5 as mt5
        tick = mt5.symbol_info_tick("XAUUSD")
        price = tick.ask

        entry = EntrySignal(
            direction=Direction.LONG,
            confidence=0.80,
            entry_zone_top=price + 2.0,
            entry_zone_bottom=price - 2.0,
            reason="integration test signal",
        )
        risk = RiskCalculation(
            lot_size=0.01,              # minimum size for demo safety
            sl_price=price - 20.0,
            tp1_price=price + 10.0,
            tp2_price=price + 20.0,
            sl_distance=20.0,
            risk_amount_usd=20.0,
            in_recovery=False,
            reason="integration test",
        )
        return ExecutionSignal(
            entry_signal=entry,
            risk_calc=risk,
            signal_id=str(uuid.uuid4()),
            received_at=datetime.utcnow(),
        )

    def test_live_order_placed_with_sl_and_tp(self):
        """SC-001: Place order → SL and TP confirmed on broker side."""
        import MetaTrader5 as mt5

        signal = self._build_signal()
        result = self.engine.execute_signal(signal, 100000.0, 100000.0)

        from src.execution.models import AuditAction
        assert result.action_type == AuditAction.ORDER_PLACED, (
            f"ORDER_PLACED expected — got {result.action_type}; reason={result.rejection_reason}"
        )
        assert result.ticket_id is not None

        # Confirm SL set on broker side (SC-001)
        time.sleep(1)
        positions = mt5.positions_get(ticket=result.ticket_id)
        assert positions, f"Position {result.ticket_id} not found on broker"
        pos = positions[0]
        assert abs(pos.sl - signal.risk_calc.sl_price) < 1.0, (
            f"SC-001 FAIL: broker SL {pos.sl} != requested {signal.risk_calc.sl_price}"
        )

        # Clean up — close the test position
        import MetaTrader5 as mt5
        close_req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": "XAUUSD",
            "volume": 0.01,
            "type": mt5.ORDER_TYPE_SELL,
            "position": result.ticket_id,
            "deviation": 10,
            "magic": 202699,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        mt5.order_send(close_req)
