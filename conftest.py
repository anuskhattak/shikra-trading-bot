"""
Root conftest — session-wide MT5 mock.

MetaTrader5 is a Windows-only broker library not available in CI or dev
environments without a live terminal. Registering a permanent mock here
lets @patch("src.broker.*.mt5") decorators resolve the module path without
triggering a real MT5 import on every test setup.
"""
import sys
from unittest.mock import MagicMock


def pytest_configure(config):
    mock_mt5 = MagicMock()
    mock_mt5.TIMEFRAME_D1 = 16408
    mock_mt5.TIMEFRAME_H4 = 16388
    mock_mt5.TIMEFRAME_H1 = 16385
    mock_mt5.ORDER_TYPE_BUY = 0
    mock_mt5.ORDER_TYPE_SELL = 1
    mock_mt5.TRADE_ACTION_DEAL = 1
    mock_mt5.ORDER_TIME_GTC = 1
    mock_mt5.ORDER_FILLING_IOC = 1
    mock_mt5.TRADE_RETCODE_DONE = 10009
    mock_mt5.TRADE_RETCODE_NO_MONEY = 10019
    sys.modules["MetaTrader5"] = mock_mt5
