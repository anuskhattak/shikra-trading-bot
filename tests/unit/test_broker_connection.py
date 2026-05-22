"""
Unit tests for BrokerConnection — US1 + US4: Connection & Health Monitoring.

TDD: tests written before implementation. No live MT5 terminal required.
"""
import json
import time as _time
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from loguru import logger

import src.broker.connection as conn_module
from src.broker.connection import BrokerConnection, ConnectionStatus


# ---------------------------------------------------------------------------
# Session-wide fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _redirect_event_log(tmp_path, monkeypatch):
    """Redirect connection_events.json away from the repo for every test."""
    monkeypatch.setattr(
        BrokerConnection,
        "_event_log_path",
        tmp_path / "connection_events.json",
    )


@pytest.fixture
def loguru_sink():
    """Capture all loguru output as a list of formatted strings."""
    messages: list[str] = []
    handler_id = logger.add(messages.append, level="DEBUG", colorize=False)
    yield messages
    logger.remove(handler_id)


# ---------------------------------------------------------------------------
# T005 — Successful connection and authentication
# ---------------------------------------------------------------------------

class TestConnectSuccess:
    @patch("src.broker.connection.mt5")
    def test_connect_success(self, mock_mt5, monkeypatch):
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        monkeypatch.setattr(BrokerConnection, "_start_health_monitor", lambda _: None)

        conn = BrokerConnection(account=111, password="pw", server="srv")
        result = conn.connect()

        assert result is True
        assert conn.status == ConnectionStatus.CONNECTED


# ---------------------------------------------------------------------------
# T006 — Authentication failure (wrong password)
# ---------------------------------------------------------------------------

class TestConnectAuthFailure:
    @patch("src.broker.connection.mt5")
    def test_connect_auth_failure(self, mock_mt5, loguru_sink):
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = False
        mock_mt5.last_error.return_value = (10013, "Invalid account")

        conn = BrokerConnection(account=111, password="pw", server="srv")
        result = conn.connect()

        assert result is False
        assert conn.status == ConnectionStatus.DISCONNECTED
        assert any("Authentication Failed" in m for m in loguru_sink)


# ---------------------------------------------------------------------------
# T007 — Terminal unavailable (MT5 not installed / not running)
# ---------------------------------------------------------------------------

class TestConnectTerminalUnavailable:
    @patch("src.broker.connection.mt5")
    def test_connect_terminal_unavailable(self, mock_mt5, loguru_sink):
        mock_mt5.initialize.return_value = False

        conn = BrokerConnection(account=111, password="pw", server="srv")
        result = conn.connect()

        assert result is False
        assert any("Terminal Unavailable" in m for m in loguru_sink)


# ---------------------------------------------------------------------------
# T008 — Connection timeout (MT5 initialize hangs > 10 s)
# ---------------------------------------------------------------------------

class TestConnectTimeout:
    @patch("src.broker.connection.mt5")
    def test_connect_timeout(self, mock_mt5, loguru_sink, monkeypatch):
        """SC-001 edge: FuturesTimeoutError must be caught, logged, return False."""

        def raise_timeout(self_inner, fn, timeout):
            raise FuturesTimeoutError()

        monkeypatch.setattr(BrokerConnection, "_call_with_timeout", raise_timeout)

        conn = BrokerConnection(account=111, password="pw", server="srv")
        result = conn.connect()

        assert result is False
        assert conn.status == ConnectionStatus.DISCONNECTED
        assert any("Connection Timeout" in m for m in loguru_sink)


# ---------------------------------------------------------------------------
# T009 — from_env() loads credentials from environment
# ---------------------------------------------------------------------------

class TestFromEnv:
    def test_from_env_loads_credentials(self, monkeypatch):
        monkeypatch.setenv("MT5_ACCOUNT", "111")
        monkeypatch.setenv("MT5_PASSWORD", "pass")
        monkeypatch.setenv("MT5_SERVER", "srv")

        conn = BrokerConnection.from_env()

        assert conn._account == 111
        assert conn._password == "pass"
        assert conn._server == "srv"


# ---------------------------------------------------------------------------
# T010 — Connection event persisted to connection_events.json
# ---------------------------------------------------------------------------

class TestEventPersistedToFile:
    @patch("src.broker.connection.mt5")
    def test_event_persisted_to_file(self, mock_mt5, tmp_path, monkeypatch):
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        monkeypatch.setattr(BrokerConnection, "_start_health_monitor", lambda _: None)

        conn = BrokerConnection(account=111, password="pw", server="srv")
        conn.connect()

        event_log = tmp_path / "connection_events.json"  # redirected by autouse fixture
        assert event_log.exists()
        records = json.loads(event_log.read_text())
        assert len(records) >= 1
        assert records[0]["event_type"] == "connected"


# ---------------------------------------------------------------------------
# T010b — Password must never appear in any log output (NFR-001)
# ---------------------------------------------------------------------------

class TestCredentialsAbsentFromLogs:
    @patch("src.broker.connection.mt5")
    def test_credentials_absent_from_logs(self, mock_mt5, loguru_sink):
        """NFR-001 regression guard: credentials must be masked at all times."""
        secret_password = "SuperSecret123!"
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = False
        mock_mt5.last_error.return_value = (10013, "Invalid account")

        conn = BrokerConnection(account=111, password=secret_password, server="srv")
        conn.connect()

        all_logs = "".join(loguru_sink)
        assert secret_password not in all_logs
        assert "MT5_PASSWORD" not in all_logs


# ---------------------------------------------------------------------------
# T026 — Health check failure triggers RECONNECTING status
# ---------------------------------------------------------------------------

class TestHealthCheckTriggersReconnect:
    @patch("src.broker.connection.mt5")
    def test_health_check_triggers_reconnect(self, mock_mt5, monkeypatch):
        """FR-010: failed ping must immediately set RECONNECTING before retrying."""
        conn = BrokerConnection(account=111, password="pw", server="srv")
        conn._status = ConnectionStatus.CONNECTED

        monkeypatch.setattr(BrokerConnection, "HEALTH_CHECK_INTERVAL", 0)
        monkeypatch.setattr(conn, "_ping", lambda: False)

        def fake_reconnect():
            conn._stop_event.set()  # stop loop after first failure

        monkeypatch.setattr(conn, "_reconnect_loop", fake_reconnect)

        conn._health_loop()

        assert conn.status == ConnectionStatus.RECONNECTING


# ---------------------------------------------------------------------------
# T027 — 3 consecutive failures → EMERGENCY_STOP within 35 s
# ---------------------------------------------------------------------------

class TestEmergencyStopAfter3Failures:
    @patch("src.broker.connection.mt5")
    def test_emergency_stop_after_3_failures(self, mock_mt5, loguru_sink, monkeypatch):
        """SC-005: 3 failed reconnects must reach EMERGENCY_STOP within 30 s budget."""
        monkeypatch.setattr(conn_module.time, "sleep", lambda s: None)  # instant sleep
        mock_mt5.initialize.return_value = False
        mock_mt5.last_error.return_value = (10013, "error")

        conn = BrokerConnection(account=111, password="pw", server="srv")

        start = _time.time()
        conn._reconnect_loop()
        elapsed = _time.time() - start

        assert conn.status == ConnectionStatus.EMERGENCY_STOP
        assert any("EMERGENCY STOP" in m for m in loguru_sink)
        assert elapsed <= 35


# ---------------------------------------------------------------------------
# T028 — disconnect() cleanly releases MT5 and sets stop event
# ---------------------------------------------------------------------------

class TestDisconnectClean:
    @patch("src.broker.connection.mt5")
    def test_disconnect_clean(self, mock_mt5):
        """FR-013: disconnect must stop health monitor and release MT5 cleanly."""
        conn = BrokerConnection(account=111, password="pw", server="srv")
        conn._status = ConnectionStatus.CONNECTED

        conn.disconnect()

        mock_mt5.shutdown.assert_called_once()
        assert conn.status == ConnectionStatus.DISCONNECTED
        assert conn._stop_event.is_set()


# ---------------------------------------------------------------------------
# T029 — uptime_percent returns correct session ratio
# ---------------------------------------------------------------------------

class TestUptimePercent:
    def test_uptime_percent(self, monkeypatch):
        """NFR-002: uptime tracking must reflect connected seconds vs total session."""
        fixed_now = datetime(2026, 5, 12, 12, 0, 0)

        conn = BrokerConnection(account=111, password="pw", server="srv")
        conn._session_start = fixed_now - timedelta(seconds=100)
        conn._connected_seconds = 90.0

        # Freeze utcnow so the ratio is deterministic (avoids flakiness)
        class _FrozenDt:
            @staticmethod
            def utcnow():
                return fixed_now

        monkeypatch.setattr(conn_module, "datetime", _FrozenDt)

        assert conn.uptime_percent == 90.0
