"""
Unit tests for OrderManager — validation logic only, no live MT5 connection.

All MT5 API calls are mocked so these tests run in CI without a broker terminal.
Focus: SL/TP geometry validation, log atomicity, and error-code mapping.
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Patch MT5 before any import so the module-level constants resolve correctly
with patch.dict("sys.modules", {"MetaTrader5": MagicMock()}):
    import MetaTrader5 as mt5
    mt5.ORDER_TYPE_BUY = 0
    mt5.ORDER_TYPE_SELL = 1
    mt5.TRADE_ACTION_DEAL = 1
    mt5.ORDER_TIME_GTC = 1
    mt5.ORDER_FILLING_IOC = 1
    mt5.TRADE_RETCODE_DONE = 10009
    mt5.TRADE_RETCODE_NO_MONEY = 10019

    from src.broker.order_manager import OrderManager, OrderType, TradeOrder


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_trades_log(tmp_path, monkeypatch):
    """Redirect trades.json to a temp directory so tests don't pollute the repo."""
    log_path = tmp_path / "trades.json"
    monkeypatch.setattr("src.broker.order_manager.TRADES_LOG", log_path)
    return log_path


@pytest.fixture
def manager():
    return OrderManager(magic_number=202605, slippage_points=5)


# ---------------------------------------------------------------------------
# SL/TP geometry validation — FR-007
# ---------------------------------------------------------------------------

class TestSlTpValidation:
    def test_buy_valid_geometry(self, manager):
        # BUY: SL below entry, TP above entry — valid
        assert manager._sl_tp_valid(OrderType.BUY, price=1900.0, sl=1880.0, tp=1940.0)

    def test_buy_sl_above_price_rejected(self, manager):
        # SL above price on a BUY makes no sense — reject
        assert not manager._sl_tp_valid(OrderType.BUY, price=1900.0, sl=1920.0, tp=1940.0)

    def test_buy_tp_below_price_rejected(self, manager):
        assert not manager._sl_tp_valid(OrderType.BUY, price=1900.0, sl=1880.0, tp=1890.0)

    def test_sell_valid_geometry(self, manager):
        # SELL: TP below entry, SL above entry — valid
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
    def test_rejected_order_logged_to_file(self, mock_mt5, manager, tmp_trades_log):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1900.0, bid=1899.0)

        # SL above price — invalid BUY
        order = manager.place_order(
            order_type=OrderType.BUY,
            volume=0.01,
            stop_loss=1920.0,   # Wrong side
            take_profit=1940.0,
        )

        assert order.result == "rejected"
        assert "Missing SL/TP" in order.error_message

        # Verify the rejection is persisted in trades.json
        records = json.loads(tmp_trades_log.read_text())
        assert len(records) == 1
        assert records[0]["result"] == "rejected"

    @patch("src.broker.order_manager.mt5")
    def test_no_price_data_causes_rejection(self, mock_mt5, manager, tmp_trades_log):
        mock_mt5.symbol_info_tick.return_value = None  # Market closed

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
    def test_successful_buy_logged(self, mock_mt5, manager, tmp_trades_log):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1900.0, bid=1899.0)
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
        assert records[0]["broker_ticket"] == 123456


# ---------------------------------------------------------------------------
# Insufficient margin — FR-016
# ---------------------------------------------------------------------------

class TestInsufficientMargin:
    @patch("src.broker.order_manager.mt5")
    def test_insufficient_margin_logged(self, mock_mt5, manager, tmp_trades_log):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1900.0, bid=1899.0)
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
# Log atomicity — NFR-005
# ---------------------------------------------------------------------------

class TestLogAtomicity:
    @patch("src.broker.order_manager.mt5")
    def test_multiple_orders_appended_not_overwritten(self, mock_mt5, manager, tmp_trades_log):
        """Each new trade appends; prior records are not overwritten."""
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1900.0, bid=1899.0)

        # Two rejections — both must survive in the log
        manager.place_order(OrderType.BUY, 0.01, stop_loss=1920.0, take_profit=1940.0)
        manager.place_order(OrderType.BUY, 0.01, stop_loss=1920.0, take_profit=1940.0)

        records = json.loads(tmp_trades_log.read_text())
        assert len(records) == 2
