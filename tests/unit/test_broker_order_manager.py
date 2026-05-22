"""
Unit tests for OrderManager — validation logic only, no live MT5 connection.

All MT5 API calls are mocked so these tests run in CI without a broker terminal.
Focus: SL/TP geometry validation, audit_logger routing (T009), and error-code mapping.

T009 changes from original: trades.json is now owned by audit_logger.AUDIT_LOG_LOCK.
  - tmp_trades_log patches src.execution.audit_logger.AUDIT_LOG_PATH (not TRADES_LOG)
  - OrderManager no longer has _log_lock; that lock lives in audit_logger
"""
import json
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from loguru import logger

import MetaTrader5 as mt5
import src.broker.order_manager as om_module
from src.broker.order_manager import OrderManager, OrderType
from src.execution.models import AuditAction


@pytest.fixture
def loguru_sink():
    """Capture loguru output for log-content assertions."""
    messages: list[str] = []
    handler_id = logger.add(messages.append, level="DEBUG", colorize=False)
    yield messages
    logger.remove(handler_id)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_trades_log(tmp_path, monkeypatch):
    """Redirect audit log to a temp path — patches audit_logger, not order_manager."""
    log_path = tmp_path / "trades.json"
    monkeypatch.setattr("src.execution.audit_logger.AUDIT_LOG_PATH", log_path)
    return log_path


@pytest.fixture
def manager():
    return OrderManager(magic_number=202605, slippage_points=5)


# ---------------------------------------------------------------------------
# SL/TP geometry validation — FR-007
# ---------------------------------------------------------------------------

class TestSlTpValidation:
    def test_buy_valid_geometry(self, manager):
        assert manager._sl_tp_valid(OrderType.BUY, price=1900.0, sl=1880.0, tp=1940.0)

    def test_buy_sl_above_price_rejected(self, manager):
        assert not manager._sl_tp_valid(OrderType.BUY, price=1900.0, sl=1920.0, tp=1940.0)

    def test_buy_tp_below_price_rejected(self, manager):
        assert not manager._sl_tp_valid(OrderType.BUY, price=1900.0, sl=1880.0, tp=1890.0)

    def test_sell_valid_geometry(self, manager):
        assert manager._sl_tp_valid(OrderType.SELL, price=1900.0, sl=1920.0, tp=1860.0)

    def test_sell_sl_below_price_rejected(self, manager):
        assert not manager._sl_tp_valid(OrderType.SELL, price=1900.0, sl=1880.0, tp=1860.0)

    def test_zero_sl_always_rejected(self, manager):
        assert not manager._sl_tp_valid(OrderType.BUY, price=1900.0, sl=0.0, tp=1940.0)

    def test_zero_tp_always_rejected(self, manager):
        assert not manager._sl_tp_valid(OrderType.BUY, price=1900.0, sl=1880.0, tp=0.0)

    def test_negative_sl_rejected(self, manager):
        assert not manager._sl_tp_valid(OrderType.BUY, price=1900.0, sl=-10.0, tp=1940.0)


# ---------------------------------------------------------------------------
# Order rejection logging — FR-007 + FR-009
# ---------------------------------------------------------------------------

class TestOrderRejection:
    @patch("src.broker.order_manager.mt5")
    def test_rejected_order_logged_as_order_rejected(self, mock_mt5, manager, tmp_trades_log):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1900.0, bid=1899.0)

        order = manager.place_order(
            order_type=OrderType.BUY,
            volume=0.01,
            stop_loss=1920.0,   # Wrong side
            take_profit=1940.0,
        )

        assert order.result == "rejected"
        assert "Missing SL/TP" in order.error_message

        records = json.loads(tmp_trades_log.read_text())
        assert len(records) == 1
        assert records[0]["action_type"] == AuditAction.ORDER_REJECTED.value
        assert records[0]["rejection_reason"] is not None

    @patch("src.broker.order_manager.mt5")
    def test_no_price_data_causes_rejection(self, mock_mt5, manager, tmp_trades_log):
        mock_mt5.symbol_info_tick.return_value = None

        order = manager.place_order(
            order_type=OrderType.BUY,
            volume=0.01,
            stop_loss=1880.0,
            take_profit=1940.0,
        )

        assert order.result == "rejected"


# ---------------------------------------------------------------------------
# Successful order submission — SC-004
# ---------------------------------------------------------------------------

class TestSuccessfulOrder:
    @patch("src.broker.order_manager.mt5")
    def test_successful_buy_logged_as_order_placed(self, mock_mt5, manager, tmp_trades_log):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1900.0, bid=1899.0)
        mock_mt5.account_info.return_value = MagicMock(margin=5000.0, margin_level=100.0)
        sym = MagicMock()
        sym.point = 0.01
        sym.trade_contract_size = 100.0
        mock_mt5.symbol_info.return_value = sym

        send_result = MagicMock()
        send_result.retcode = mt5.TRADE_RETCODE_DONE
        send_result.order = 123456
        mock_mt5.order_send.return_value = send_result
        mock_mt5.TRADE_RETCODE_DONE = mt5.TRADE_RETCODE_DONE

        order = manager.place_order(
            order_type=OrderType.BUY,
            volume=0.01,
            stop_loss=1880.0,
            take_profit=1940.0,
        )

        assert order.result == "success"
        assert order.broker_ticket == 123456

        records = json.loads(tmp_trades_log.read_text())
        assert records[0]["action_type"] == AuditAction.ORDER_PLACED.value
        assert records[0]["ticket_id"] == 123456


# ---------------------------------------------------------------------------
# Insufficient margin — FR-016
# ---------------------------------------------------------------------------

class TestInsufficientMargin:
    @patch("src.broker.order_manager.mt5")
    def test_insufficient_margin_logged_as_order_rejected(self, mock_mt5, manager, tmp_trades_log):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1900.0, bid=1899.0)
        mock_mt5.account_info.return_value = MagicMock(margin=5000.0, margin_level=100.0)
        sym = MagicMock()
        sym.point = 0.01
        sym.trade_contract_size = 100.0
        mock_mt5.symbol_info.return_value = sym

        send_result = MagicMock()
        send_result.retcode = mt5.TRADE_RETCODE_NO_MONEY
        mock_mt5.order_send.return_value = send_result
        mock_mt5.TRADE_RETCODE_DONE = mt5.TRADE_RETCODE_DONE
        mock_mt5.TRADE_RETCODE_NO_MONEY = mt5.TRADE_RETCODE_NO_MONEY

        order = manager.place_order(
            order_type=OrderType.BUY,
            volume=0.01,
            stop_loss=1880.0,
            take_profit=1940.0,
        )

        assert order.result == "failed"
        assert "Insufficient Margin" in order.error_message


# ---------------------------------------------------------------------------
# Audit log routing — T009: single lock, no _log_lock on OrderManager
# ---------------------------------------------------------------------------

class TestAuditLogRouting:
    def test_order_manager_has_no_log_lock(self, manager):
        """T009: _log_lock must be removed — AUDIT_LOG_LOCK in audit_logger owns the file."""
        assert not hasattr(manager, "_log_lock"), "_log_lock must not exist on OrderManager"

    @patch("src.broker.order_manager.mt5")
    def test_routes_through_audit_logger_write_audit_entry(self, mock_mt5, manager, monkeypatch):
        """Verify _log_trade() calls write_audit_entry, not a local file write."""
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1900.0, bid=1899.0)

        calls: list = []
        monkeypatch.setattr(
            "src.broker.order_manager.write_audit_entry",
            lambda entry, *a, **kw: calls.append(entry),
        )

        manager.place_order(OrderType.BUY, 0.01, stop_loss=1920.0, take_profit=1940.0)

        assert len(calls) == 1
        assert calls[0].action_type == AuditAction.ORDER_REJECTED


# ---------------------------------------------------------------------------
# Log atomicity — NFR-005
# ---------------------------------------------------------------------------

class TestLogAtomicity:
    @patch("src.broker.order_manager.mt5")
    def test_multiple_orders_appended_not_overwritten(self, mock_mt5, manager, tmp_trades_log):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1900.0, bid=1899.0)

        manager.place_order(OrderType.BUY, 0.01, stop_loss=1920.0, take_profit=1940.0)
        manager.place_order(OrderType.BUY, 0.01, stop_loss=1920.0, take_profit=1940.0)

        records = json.loads(tmp_trades_log.read_text())
        assert len(records) == 2


# ---------------------------------------------------------------------------
# T022 — order_send timeout → result="timeout" + logged
# ---------------------------------------------------------------------------

class TestOrderSendTimeout:
    @patch("src.broker.order_manager.mt5")
    def test_order_send_timeout(self, mock_mt5, manager, tmp_trades_log, loguru_sink, monkeypatch):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1900.0, bid=1899.0)
        mock_mt5.account_info.return_value = MagicMock(margin=5000.0, margin_level=100.0)
        monkeypatch.setattr(
            om_module, "_call_with_timeout",
            lambda fn, timeout: (_ for _ in ()).throw(FuturesTimeoutError()),
        )

        order = manager.place_order(OrderType.BUY, 0.01, stop_loss=1880.0, take_profit=1940.0)

        assert order.result == "timeout"
        assert "Order Timeout" in order.error_message
        assert any("Order Timeout" in m for m in loguru_sink)


# ---------------------------------------------------------------------------
# T023 — timeout scenario writes ORDER_REJECTED to audit log
# ---------------------------------------------------------------------------

class TestOrderTimeoutLoggedToFile:
    @patch("src.broker.order_manager.mt5")
    def test_order_timeout_logged_to_file(self, mock_mt5, manager, tmp_trades_log, monkeypatch):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1900.0, bid=1899.0)
        mock_mt5.account_info.return_value = MagicMock(margin=5000.0, margin_level=100.0)
        monkeypatch.setattr(
            om_module, "_call_with_timeout",
            lambda fn, timeout: (_ for _ in ()).throw(FuturesTimeoutError()),
        )

        manager.place_order(OrderType.BUY, 0.01, stop_loss=1880.0, take_profit=1940.0)

        records = json.loads(tmp_trades_log.read_text())
        assert len(records) == 1
        assert records[0]["action_type"] == AuditAction.ORDER_REJECTED.value
        assert records[0]["rejection_reason"] is not None


# ---------------------------------------------------------------------------
# T024b — low margin blocks order before order_send is called
# ---------------------------------------------------------------------------

class TestMarginCheckBlocksOrder:
    @patch("src.broker.order_manager.mt5")
    def test_margin_check_blocks_order(self, mock_mt5, manager, tmp_trades_log):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1900.0, bid=1899.0)
        mock_mt5.account_info.return_value = MagicMock(margin=5000.0, margin_level=8.0)

        order = manager.place_order(OrderType.BUY, 0.01, stop_loss=1880.0, take_profit=1940.0)

        assert order.result == "rejected"
        assert "Low Margin" in order.error_message
        mock_mt5.order_send.assert_not_called()
