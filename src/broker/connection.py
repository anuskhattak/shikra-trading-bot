"""
MT5 broker connection handler.

Manages the full lifecycle of the MetaTrader 5 terminal connection:
authentication, continuous health monitoring, automatic reconnection,
and clean shutdown. Credentials are never logged — masked at all times.
"""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import MetaTrader5 as mt5
from dotenv import load_dotenv
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

    # T012: shared lock + path for atomic event log writes
    _event_log_lock = threading.Lock()
    _event_log_path = Path("logs/connection_events.json")

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

        # T030: uptime tracking fields — set when connect() is called
        self._session_start: Optional[datetime] = None
        self._connected_seconds: float = 0.0

        # Ensure logs/ exists before any event writes (connection_events.json)
        Path("logs").mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    @property
    def is_connected(self) -> bool:
        return self._status == ConnectionStatus.CONNECTED

    @property
    def uptime_percent(self) -> float:
        """T033: Ratio of connected seconds to total session seconds (NFR-002)."""
        if self._session_start is None:
            return 0.0
        total = (datetime.utcnow() - self._session_start).total_seconds()
        return round((self._connected_seconds / total) * 100, 2) if total > 0 else 100.0

    @classmethod
    def from_env(cls) -> "BrokerConnection":
        """T011: Factory that reads credentials from environment (never hardcoded)."""
        load_dotenv()
        try:
            account = int(os.environ["MT5_ACCOUNT"])
            password = os.environ["MT5_PASSWORD"]
            server = os.environ["MT5_SERVER"]
        except KeyError as exc:
            raise KeyError(
                f"Missing required env var {exc} — set MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER"
            ) from exc
        return cls(account=account, password=password, server=server)

    def connect(self) -> bool:
        """
        Initialize MT5 terminal and authenticate with broker credentials.

        Returns True on success so the caller can proceed to market data.
        On any failure the system halts — no trading without authentication (FR-003).
        """
        self._session_start = datetime.utcnow()  # T031: anchor for uptime calculation
        self._status = ConnectionStatus.CONNECTING
        logger.info("Connecting to MT5 terminal...")

        # T015: timeout-guard initialize — hangs up to 10 s before raising
        try:
            initialized = self._call_with_timeout(mt5.initialize, timeout=10.0)
        except FuturesTimeoutError:
            self._record("failed", "Connection Timeout — MT5 initialize did not respond within 10s")
            logger.error("Connection Timeout — MT5 initialize did not respond within 10s")
            self._status = ConnectionStatus.DISCONNECTED
            return False

        if not initialized:
            self._record("failed", f"MT5 initialize() failed: {mt5.last_error()}")
            logger.error("Terminal Unavailable — MT5 could not initialize")
            self._status = ConnectionStatus.DISCONNECTED
            return False

        # T016: timeout-guard login — hangs up to 10 s before raising
        try:
            authorized = self._call_with_timeout(
                lambda: mt5.login(self._account, self._password, self._server),
                timeout=10.0,
            )
        except FuturesTimeoutError:
            self._record("failed", "Connection Timeout — MT5 login did not respond within 10s")
            logger.error("Connection Timeout — MT5 login did not respond within 10s")
            mt5.shutdown()
            self._status = ConnectionStatus.DISCONNECTED
            return False

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
            logger.info(f"Session uptime: {self.uptime_percent}% — disconnecting")
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
            else:
                # T032: accumulate connected time for uptime tracking — NFR-002
                self._connected_seconds += self.HEALTH_CHECK_INTERVAL

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

    def _call_with_timeout(self, fn, timeout: float):
        """Run fn() in a thread; raise FuturesTimeoutError if it exceeds timeout seconds."""
        with ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(fn).result(timeout=timeout)

    def _log_event_to_file(self, event: ConnectionEvent) -> None:
        """T013: Append event to connection_events.json atomically under lock."""
        entry = {
            "event_type": event.event_type,
            "timestamp": event.timestamp.isoformat(),
            "error_message": event.error_message,
        }
        try:
            with self._event_log_lock:
                existing: list = []
                if self._event_log_path.exists():
                    try:
                        existing = json.loads(self._event_log_path.read_text())
                    except json.JSONDecodeError:
                        existing = []
                existing.append(entry)
                self._event_log_path.write_text(json.dumps(existing, indent=2))
        except OSError as exc:
            # Trading must continue even if log write fails — warn only (spec edge case)
            logger.warning(f"Event Log Write Failed — {exc}")

    def _record(self, event_type: str, error_message: Optional[str] = None) -> None:
        # T014: persist every event to disk for auditability
        event = ConnectionEvent(event_type=event_type, error_message=error_message)
        self._events.append(event)
        self._log_event_to_file(event)
