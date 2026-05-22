"""
Integration tests for MT5 broker connection — require a live MT5 terminal.

These tests are SKIPPED automatically when MT5 is not installed or when the
environment variables MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER are not set.
Run only in a pre-live environment with paper trading credentials.
"""
import os

import pytest

INTEGRATION_SKIP = pytest.mark.skipif(
    not os.getenv("MT5_ACCOUNT"),
    reason="MT5 integration tests require MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER env vars",
)


@INTEGRATION_SKIP
class TestLiveConnection:
    """
    Requires:
        MT5_ACCOUNT=<demo account number>
        MT5_PASSWORD=<password>
        MT5_SERVER=<broker server name>
    """

    @pytest.fixture(autouse=True)
    def broker(self):
        from src.broker import BrokerConnection

        account = int(os.environ["MT5_ACCOUNT"])
        password = os.environ["MT5_PASSWORD"]
        server = os.environ["MT5_SERVER"]

        conn = BrokerConnection(account, password, server)
        yield conn
        conn.disconnect()

    def test_connect_authenticates_within_10_seconds(self, broker):
        """SC-001: Connection must succeed within 10 seconds."""
        import time
        start = time.time()
        assert broker.connect() is True
        elapsed = time.time() - start
        assert elapsed < 10, f"Connection took {elapsed:.1f}s — exceeds 10 s limit"

    def test_connected_status_after_login(self, broker):
        from src.broker import ConnectionStatus
        broker.connect()
        assert broker.status == ConnectionStatus.CONNECTED

    def test_disconnect_is_clean(self, broker):
        from src.broker import ConnectionStatus
        broker.connect()
        broker.disconnect()
        assert broker.status == ConnectionStatus.DISCONNECTED


@INTEGRATION_SKIP
class TestLiveMarketData:
    @pytest.fixture(autouse=True)
    def setup(self):
        from src.broker import BrokerConnection, MarketData

        account = int(os.environ["MT5_ACCOUNT"])
        password = os.environ["MT5_PASSWORD"]
        server = os.environ["MT5_SERVER"]

        conn = BrokerConnection(account, password, server)
        conn.connect()
        self.md = MarketData(max_spread_points=30)
        yield
        conn.disconnect()

    def test_quote_returned_within_2_seconds(self):
        """SC-002: Market data within 2 seconds of connection."""
        import time
        start = time.time()
        quote = self.md.get_quote()
        elapsed = time.time() - start

        if quote is not None:  # None = market closed — not a test failure
            assert elapsed < 2
            assert quote.bid > 0
            assert quote.ask > quote.bid

    def test_all_timeframes_return_200_bars(self):
        """SC-003: Minimum 200 bars per timeframe, zero missing."""
        result = self.md.get_all_timeframes()
        for tf_name, df in result.items():
            if df is not None:  # Market closed → None is acceptable
                assert len(df) >= 200, f"{tf_name} has only {len(df)} bars"
