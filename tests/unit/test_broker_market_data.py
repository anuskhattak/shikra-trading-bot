"""
Unit tests for MarketData — spread guard, bar count guard, market-closed detection.

All MT5 API calls are mocked. No live broker connection required.
"""
from concurrent.futures import TimeoutError as FuturesTimeoutError
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from loguru import logger

import MetaTrader5 as mt5
import src.broker.market_data as md_module
from src.broker.market_data import MarketData, Timeframe, MIN_BARS


@pytest.fixture
def loguru_sink():
    """Capture all loguru output for log-content assertions."""
    messages: list[str] = []
    handler_id = logger.add(messages.append, level="DEBUG", colorize=False)
    yield messages
    logger.remove(handler_id)


def _make_rates(count: int) -> list[dict]:
    """Generate fake OHLCV rate rows for mocking mt5.copy_rates_from_pos."""
    import time as _time
    base = int(_time.time()) - count * 3600
    rows = []
    for i in range(count):
        rows.append({
            "time": base + i * 3600,
            "open": 1900.0,
            "high": 1910.0,
            "low": 1890.0,
            "close": 1905.0,
            "tick_volume": 1000,
        })
    return rows


# ---------------------------------------------------------------------------
# Spread guard — FR-015
# ---------------------------------------------------------------------------

class TestSpreadGuard:
    @patch("src.broker.market_data.mt5")
    def test_spread_within_limit_returns_quote(self, mock_mt5):
        tick = MagicMock(bid=1900.0, ask=1900.20, time=1715000000)
        sym = MagicMock(point=0.01)
        mock_mt5.symbol_info_tick.return_value = tick
        mock_mt5.symbol_info.return_value = sym

        md = MarketData(max_spread_points=30)
        quote = md.get_quote()

        assert quote is not None
        assert quote.bid == 1900.0
        assert quote.ask == 1900.20
        assert quote.spread_points == 20   # (1900.20 - 1900.00) / 0.01

    @patch("src.broker.market_data.mt5")
    def test_spread_above_limit_returns_none(self, mock_mt5):
        tick = MagicMock(bid=1900.0, ask=1900.50, time=1715000000)
        sym = MagicMock(point=0.01)
        mock_mt5.symbol_info_tick.return_value = tick
        mock_mt5.symbol_info.return_value = sym

        md = MarketData(max_spread_points=30)
        quote = md.get_quote()

        assert quote is None  # 50 pts > 30 max — trade must be skipped

    @patch("src.broker.market_data.mt5")
    def test_no_tick_returns_none(self, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = None
        md = MarketData()
        assert md.get_quote() is None


# ---------------------------------------------------------------------------
# Bar count guard — FR-005
# ---------------------------------------------------------------------------

class TestBarCountGuard:
    @patch("src.broker.market_data.mt5")
    def test_sufficient_bars_returns_dataframe(self, mock_mt5):
        mock_mt5.copy_rates_from_pos.return_value = _make_rates(200)

        md = MarketData()
        df = md.get_ohlcv(Timeframe.H1, count=200)

        assert df is not None
        assert len(df) == 200
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]

    @patch("src.broker.market_data.mt5")
    def test_insufficient_bars_returns_none(self, mock_mt5):
        # Only 150 bars available — must reject rather than silently use partial data
        mock_mt5.copy_rates_from_pos.return_value = _make_rates(150)

        md = MarketData()
        df = md.get_ohlcv(Timeframe.D1, count=200)

        assert df is None

    @patch("src.broker.market_data.mt5")
    def test_none_from_mt5_returns_none(self, mock_mt5):
        mock_mt5.copy_rates_from_pos.return_value = None

        md = MarketData()
        df = md.get_ohlcv(Timeframe.H4, count=200)

        assert df is None


# ---------------------------------------------------------------------------
# Market open / closed — edge case
# ---------------------------------------------------------------------------

class TestMarketOpen:
    @patch("src.broker.market_data.mt5")
    def test_open_when_tick_present(self, mock_mt5):
        mock_mt5.symbol_info.return_value = MagicMock()
        mock_mt5.symbol_info_tick.return_value = MagicMock()

        md = MarketData()
        assert md.is_market_open() is True

    @patch("src.broker.market_data.mt5")
    def test_closed_when_no_tick(self, mock_mt5):
        mock_mt5.symbol_info.return_value = MagicMock()
        mock_mt5.symbol_info_tick.return_value = None  # Weekend / holiday

        md = MarketData()
        assert md.is_market_open() is False

    @patch("src.broker.market_data.mt5")
    def test_closed_when_symbol_unavailable(self, mock_mt5):
        mock_mt5.symbol_info.return_value = None

        md = MarketData()
        assert md.is_market_open() is False


# ---------------------------------------------------------------------------
# All-timeframe fetch — signal engine dependency
# ---------------------------------------------------------------------------

class TestGetAllTimeframes:
    @patch("src.broker.market_data.mt5")
    def test_all_three_present(self, mock_mt5):
        mock_mt5.copy_rates_from_pos.return_value = _make_rates(200)

        md = MarketData()
        result = md.get_all_timeframes()

        assert set(result.keys()) == {"D1", "H4", "H1"}
        assert all(v is not None for v in result.values())

    @patch("src.broker.market_data.mt5")
    def test_one_missing_reported(self, mock_mt5):
        # H1 returns insufficient bars — should appear as None in result
        def side_effect(symbol, tf, pos, count):
            if tf == mt5.TIMEFRAME_H1:
                return _make_rates(50)  # Too few
            return _make_rates(200)

        mock_mt5.copy_rates_from_pos.side_effect = side_effect

        md = MarketData()
        result = md.get_all_timeframes()

        assert result["H1"] is None
        assert result["D1"] is not None
        assert result["H4"] is not None


# ---------------------------------------------------------------------------
# T017 — get_quote() timeout (symbol_info_tick hangs > 2 s)
# ---------------------------------------------------------------------------

class TestGetQuoteTimeout:
    @patch("src.broker.market_data.mt5")
    def test_get_quote_timeout(self, mock_mt5, loguru_sink, monkeypatch):
        """SC-002 edge: hung tick call must be cut off, logged, return None."""
        monkeypatch.setattr(md_module, "_call_with_timeout",
                            lambda fn, timeout: (_ for _ in ()).throw(FuturesTimeoutError()))

        md = MarketData()
        result = md.get_quote()

        assert result is None
        assert any("Market Data Timeout" in m for m in loguru_sink)


# ---------------------------------------------------------------------------
# T018 — get_ohlcv() timeout (copy_rates_from_pos hangs > 2 s)
# ---------------------------------------------------------------------------

class TestGetOhlcvTimeout:
    @patch("src.broker.market_data.mt5")
    def test_get_ohlcv_timeout(self, mock_mt5, monkeypatch):
        """copy_rates_from_pos hang must return None, not block the engine."""
        monkeypatch.setattr(md_module, "_call_with_timeout",
                            lambda fn, timeout: (_ for _ in ()).throw(FuturesTimeoutError()))

        md = MarketData()
        result = md.get_ohlcv(Timeframe.H1)

        assert result is None
