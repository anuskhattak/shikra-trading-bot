"""
MT5 broker connection handler.

Manages the full lifecycle of the MetaTrader 5 terminal connection:
authentication, continuous health monitoring, automatic reconnection,
and clean shutdown. Credentials are never logged — masked at all times.
"""
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

import MetaTrader5 as mt5
from loguru import logger


class ConnectionStatus(Enum):
    DISCONNECTED = "Disconnected"
    CONNECTING = "Connecting"
    CONNECTED = "Connected"
    RECONNECTING = "Reconnecting"
    EMERGENCY_STOP = "EmergencyStop"


@dataclass
class ConnectionEvent:
    event_type: str  # connected / disconnected / reconnected / failed
    timestamp: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None


class BrokerConnection:
    """
    MT5 terminal connection with automatic health monitoring and reconnection.

    Health monitor runs as a daemon thread every HEALTH_CHECK_INTERVAL seconds.
    After MAX_RECONNECT_ATTEMPTS consecutive failures, enters emergency stop — no
    further trading until manual intervention, per SC-008.
    """

    MAX_RECONNECT_ATTEMPTS = 3
    HEALTH_CHECK_INTERVAL = 10   # Detect loss within 10 s — FR-010
    RECONNECT_PAUSE = 10         # Pause between attempts; 3 × 10 s ≤ 30 s — SC-005

    def __init__(self, account: int, password: str, server: str) -> None:
        # Credentials held in memory only — never passed to logger
        self._account = account
        self._password = password
        self._server = server

        self._status = ConnectionStatus.DISCONNECTED
        self._connected_at: Optional[datetime] = None
        self._stop_event = threading.Event()
        self._health_thread: Optional[threading.Thread] = None
        self._events: list[ConnectionEvent] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    @property
    def is_connected(self) -> bool:
        return self._status == ConnectionStatus.CONNECTED

    def connect(self) -> bool:
        """
        Initialize MT5 terminal and authenticate with broker credentials.

        Returns True on success so the caller can proceed to market data.
        On any failure the system halts — no trading without authentication (FR-003).
        """
        self._status = ConnectionStatus.CONNECTING
        logger.info("Connecting to MT5 terminal...")

        if not mt5.initialize():
            self._record("failed", f"MT5 initialize() failed: {mt5.last_error()}")
            logger.error("Terminal Unavailable — MT5 could not initialize")
            self._status = ConnectionStatus.DISCONNECTED
            return False

        authorized = mt5.login(self._account, self._password, self._server)
        if not authorized:
            # Log only the numeric error code — never the password (NFR-001)
            code, _ = mt5.last_error()
            self._record("failed", "Authentication Failed")
            logger.error(f"Authentication Failed — error code: {code}, server: {self._server}")
            mt5.shutdown()
            self._status = ConnectionStatus.DISCONNECTED
            return False

        self._status = ConnectionStatus.CONNECTED
        self._connected_at = datetime.utcnow()
        self._record("connected")
        logger.info(f"Connected: XAUUSD ready — server: {self._server}")

        self._start_health_monitor()
        return True

    def disconnect(self) -> None:
        """
        Cleanly release the MT5 connection.

        Stops the health monitor thread first so no reconnection is triggered
        during shutdown — prevents orphaned connections (FR-013).
        """
        self._stop_event.set()
        if self._health_thread and self._health_thread.is_alive():
            self._health_thread.join(timeout=5)

        if self._status != ConnectionStatus.DISCONNECTED:
            mt5.shutdown()
            self._status = ConnectionStatus.DISCONNECTED
            self._record("disconnected")
            logger.info("Disconnected from MT5 terminal cleanly")

    # ------------------------------------------------------------------
    # Health monitoring
    # ------------------------------------------------------------------

    def _start_health_monitor(self) -> None:
        self._stop_event.clear()
        self._health_thread = threading.Thread(
            target=self._health_loop,
            daemon=True,
            name="MT5HealthMonitor",
        )
        self._health_thread.start()

    def _health_loop(self) -> None:
        """Poll terminal every HEALTH_CHECK_INTERVAL seconds; reconnect on loss."""
        while not self._stop_event.wait(self.HEALTH_CHECK_INTERVAL):
            if not self._ping():
                logger.warning("Connection loss detected — halting trading, beginning reconnection")
                self._status = ConnectionStatus.RECONNECTING
                self._record("disconnected", "Health check failed — connection dropped")
                self._reconnect_loop()

    def _ping(self) -> bool:
        """Return True when the MT5 terminal reports an active broker connection."""
        info = mt5.terminal_info()
        return info is not None and info.connected

    def _reconnect_loop(self) -> None:
        """
        Try to re-establish connection up to MAX_RECONNECT_ATTEMPTS times.
        Emergency stop is triggered when all attempts are exhausted — SC-008.
        """
        for attempt in range(1, self.MAX_RECONNECT_ATTEMPTS + 1):
            logger.info(f"Reconnection attempt {attempt}/{self.MAX_RECONNECT_ATTEMPTS}")

            # Re-initialize MT5 before each login attempt
            mt5.shutdown()
            if mt5.initialize() and mt5.login(self._account, self._password, self._server):
                self._status = ConnectionStatus.CONNECTED
                self._record("reconnected")
                logger.info(f"Reconnected successfully on attempt {attempt}")
                return

            code, _ = mt5.last_error()
            self._record("failed", f"Reconnect attempt {attempt} failed — error: {code}")
            logger.warning(f"Reconnect attempt {attempt} failed — error: {code}")
            time.sleep(self.RECONNECT_PAUSE)

        # All attempts exhausted — enter emergency stop, require manual fix
        self._status = ConnectionStatus.EMERGENCY_STOP
        self._record("failed", "Emergency Stop — 3 consecutive reconnection failures")
        logger.critical(
            "EMERGENCY STOP — 3 consecutive reconnection failures; manual intervention required"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record(self, event_type: str, error_message: Optional[str] = None) -> None:
        self._events.append(
            ConnectionEvent(event_type=event_type, error_message=error_message)
        )
