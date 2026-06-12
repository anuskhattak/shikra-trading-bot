"""Strategy Orchestrator — live trading loop tying all 6 modules together (spec009 US1).

Coordinates: BrokerConnection → ATRService → SMC engine → filters → risk → ExecutionEngine.
Bar close detection via 10-second polling. MT5ConnectionError triggers exponential backoff
reconnection up to config['orchestrator']['max_reconnect_retries'] attempts.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import MetaTrader5 as mt5
from loguru import logger

from src.analysis.atr_service import ATRService
from src.analysis.models import OHLCVBar, Timeframe
from src.broker.connection import BrokerConnection
from src.broker.order_manager import OrderManager
from src.execution.execution_engine import ExecutionEngine
from src.execution.kill_switch import is_kill_switch_active
from src.execution.models import ExecutionSignal
from src.filters.models import FilterResult
from src.filters.news_filter import load_news_calendar
from src.orchestrator.bar_monitor import MT5ConnectionError, poll_for_new_bar
from src.orchestrator.models import PipelineContext
from src.orchestrator.pipeline import run_pipeline

SYMBOL = "XAUUSD"
POLL_INTERVAL_SECONDS = 10
WARMUP_BARS = 150


class StrategyOrchestrator:
    """Main controller for live XAUUSD trading on MetaTrader 5."""

    def __init__(
        self,
        broker: BrokerConnection,
        order_manager: OrderManager,
        atr_service: ATRService,
        execution_engine: ExecutionEngine,
        config: dict,
        kill_switch_path: Optional[Path] = None,
    ) -> None:
        """Wire up all 5 service dependencies and optional kill-switch path."""
        self._broker = broker
        self._order_manager = order_manager
        self._atr_service = atr_service
        self._execution_engine = execution_engine
        self._config = config
        self._kill_switch_path = kill_switch_path

        self._last_bar_time: Optional[datetime] = None
        self._session_trades: int = 0
        self._session_start: Optional[datetime] = None
        self._day_start_equity: float = config.get("backtest", {}).get("initial_balance", 10000.0)
        self._current_equity: float = self._day_start_equity

        # Load news calendar once on startup (may be empty if file absent)
        calendar_path = config.get("filters", {}).get("news", {}).get("calendar_path", "")
        self._news_events = load_news_calendar(calendar_path) if calendar_path else []

    # ── Public API ──────────────────────────────────────────────────────────

    def run(self) -> None:
        """Main polling loop. Blocks until KeyboardInterrupt or fatal reconnect failure."""
        self._startup()
        self._session_start = datetime.now(timezone.utc)

        while True:
            try:
                time.sleep(POLL_INTERVAL_SECONDS)
                new_bar, new_time, bars_dict = poll_for_new_bar(
                    self._last_bar_time,
                    symbol=SYMBOL,
                    timeframe_mt5=Timeframe.H1.value,
                    fetch_count=WARMUP_BARS,
                )
                if new_bar:
                    self._on_new_bar(bars_dict, new_time)

            except KeyboardInterrupt:
                logger.info("KeyboardInterrupt received — shutting down")
                break

            except MT5ConnectionError as exc:
                logger.warning(f"MT5 disconnected: {exc}")
                self._reconnect()   # raises SystemExit if all retries exhausted

        self._shutdown()

    # ── Internal lifecycle ───────────────────────────────────────────────────

    def _startup(self) -> None:
        """Connect to MT5, warm up ATR cache for all 4 timeframes, log ready."""
        self._broker.connect()

        for tf in Timeframe:
            rates = mt5.copy_rates_from_pos(SYMBOL, tf.value, 0, WARMUP_BARS)
            if rates is None:
                raise MT5ConnectionError(f"Warmup failed for {tf.name} — MT5 returned None")
            bars = [OHLCVBar(
                open=float(r["open"]), high=float(r["high"]), low=float(r["low"]),
                close=float(r["close"]), volume=float(r["tick_volume"]),
                timestamp=datetime.fromtimestamp(int(r["time"]), tz=timezone.utc),
            ) for r in rates]
            self._atr_service.refresh(tf, bars)

        account = mt5.account_info()
        if account is not None:
            self._day_start_equity = float(account.equity)
            self._current_equity = self._day_start_equity

        logger.info(f"Shikra — ready (equity={self._day_start_equity:.2f})")

    def _on_new_bar(
        self,
        bars_dict: dict,
        new_bar_time: datetime,
    ) -> None:
        """Process one H1 bar close: run pipeline → execute if ALLOWED → manage positions."""
        signal_id = str(uuid.uuid4())

        # Update equity snapshot for this bar
        account = mt5.account_info()
        if account is not None:
            self._current_equity = float(account.equity)

        tick = mt5.symbol_info_tick(SYMBOL)
        spread_usd = (tick.ask - tick.bid) if tick is not None else 0.30

        ctx = PipelineContext(
            signal_id=signal_id,
            timeframe=Timeframe.H1,
            bars=bars_dict,
            now_utc=new_bar_time,   # bar close timestamp — not wall clock (FR-002, determinism)
            spread_usd=spread_usd,
            news_events=self._news_events,
            mode="live",
            balance=self._day_start_equity,
            current_equity=self._current_equity,
        )

        ctx = run_pipeline(ctx, self._atr_service, self._config)
        self._last_bar_time = new_bar_time

        logger.info(
            f"[{signal_id[:8]}] bar={new_bar_time.isoformat()} "
            f"signal={ctx.entry_signal.direction.value if ctx.entry_signal else 'NONE'} "
            f"filter={ctx.filter_result.final_result.value if ctx.filter_result else 'N/A'}"
        )

        # Order entry — kill switch prevents new entries but never blocks position management
        kill_active = (
            self._kill_switch_path is not None
            and is_kill_switch_active(self._kill_switch_path)
        )

        if not kill_active and (
            ctx.filter_result is not None
            and ctx.filter_result.final_result == FilterResult.ALLOWED
            and ctx.risk_calc is not None
        ):
            exec_signal = ExecutionSignal(
                entry_signal=ctx.entry_signal,
                risk_calc=ctx.risk_calc,
                signal_id=signal_id,
                received_at=datetime.now(timezone.utc),
            )
            # run_preflight() inside execute_signal enforces drawdown/limits (spec005)
            result = self._execution_engine.execute_signal(
                exec_signal,
                self._day_start_equity,
                self._current_equity,
            )
            if result.action_type.value == "ORDER_PLACED":
                self._session_trades += 1
        elif kill_active:
            logger.warning(f"[{signal_id[:8]}] Kill switch active — entry skipped")

        # Always manage open positions regardless of kill switch or signal state
        current_price = mt5.symbol_info_tick(SYMBOL).last
        self._execution_engine.manage_open_positions(current_price)

    def _reconnect(self) -> None:
        """Attempt broker reconnection with exponential backoff. Raises SystemExit on exhaustion."""
        orch_cfg = self._config.get("orchestrator", {})
        max_retries = int(orch_cfg.get("max_reconnect_retries", 5))
        base_seconds = float(orch_cfg.get("reconnect_backoff_base_seconds", 1))

        for attempt in range(max_retries):
            wait = base_seconds * (2 ** attempt)
            logger.warning(f"Reconnecting in {wait:.0f}s (attempt {attempt + 1}/{max_retries})")
            time.sleep(wait)
            try:
                if self._broker.connect():
                    logger.info("Reconnected to MT5 successfully — resuming")
                    return
            except Exception as exc:
                logger.error(f"Reconnect attempt {attempt + 1} failed: {exc}")

        logger.critical("Max reconnect retries exhausted — halting bot")
        raise SystemExit(1)

    def _shutdown(self) -> None:
        """Disconnect from MT5 and log session summary."""
        self._broker.disconnect()
        duration = (
            (datetime.now(timezone.utc) - self._session_start).total_seconds() / 60
            if self._session_start else 0
        )
        logger.info(
            f"Session ended — trades={self._session_trades} "
            f"duration={duration:.1f}min"
        )
