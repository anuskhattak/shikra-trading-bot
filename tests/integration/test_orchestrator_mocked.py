"""Integration tests for StrategyOrchestrator — spec009 T011.

Uses mocked MT5 + mocked module dependencies throughout (no live terminal required).
5 tests:
  1. _startup() connects broker and calls ATRService.refresh × 4 timeframes
  2. _on_new_bar() with ALLOWED signal calls execute_signal once
  3. _on_new_bar() with BLOCKED signal does NOT call execute_signal
  4. Kill switch active → execute_signal not called, manage_open_positions IS called
  5. MT5ConnectionError in polling → retries up to max_reconnect_retries; exhaustion → SystemExit
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from src.analysis.models import OHLCVBar, Timeframe
from src.engine.models import Direction, EntrySignal, SignalType
from src.execution.models import AuditAction, TradeAuditEntry
from src.filters.models import FilterDecision, FilterResult, TradeGateResult
from src.orchestrator.bar_monitor import MT5ConnectionError
from src.orchestrator.models import PipelineContext
from src.orchestrator.strategy_orchestrator import StrategyOrchestrator
from src.risk.models import RiskCalculation

_TS = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)

_CONFIG = {
    "orchestrator": {"max_reconnect_retries": 3, "reconnect_backoff_base_seconds": 0},
    "backtest": {"initial_balance": 10000.0},
    "risk": {
        "sl_atr_multiplier": 1.5, "tp1_rr_ratio": 1.5, "tp2_rr_ratio": 3.0,
        "risk_percent": 1.0, "pip_value_per_lot": 10.0,
        "max_lot_size": 5.0, "min_lot_size": 0.01,
    },
    "filters": {
        "spread": {"max_spread_usd": 0.50},
        "news": {"pre_event_minutes": 30, "post_event_minutes": 15,
                 "impact_levels": ["HIGH"], "calendar_path": ""},
        "volatility": {"atr_lookback": 14, "low_atr_ratio": 0.5, "extreme_atr_ratio": 5.0},
    },
    "analysis": {
        "atr": {"period": 14, "reference_period": 20},
        "h4_bias": {
            "lookback_bars": 20,
            "fractal_n": 2,
            "bullish_strength_threshold": 0.60,
            "bearish_strength_threshold": 0.60,
        },
    },
}


def _make_orchestrator(kill_switch_path=None) -> StrategyOrchestrator:
    broker   = MagicMock()
    order_mgr = MagicMock()
    atr_svc  = MagicMock()
    exec_eng = MagicMock()
    exec_eng.manage_open_positions.return_value = []
    return StrategyOrchestrator(
        broker, order_mgr, atr_svc, exec_eng, _CONFIG,
        kill_switch_path=kill_switch_path,
    )


def _fake_rates(ts: int = 1_000_000, count: int = 150) -> list[dict]:
    return [{"time": ts, "open": 2000.0, "high": 2010.0,
             "low": 1990.0, "close": 2005.0, "tick_volume": 100.0}] * count


def _make_bars_dict() -> dict[Timeframe, list[OHLCVBar]]:
    bar = OHLCVBar(open=2000.0, high=2010.0, low=1990.0, close=2005.0, volume=100.0, timestamp=_TS)
    return {tf: [bar] * 60 for tf in Timeframe}


def _allowed_ctx(signal_id: str = "test-001") -> PipelineContext:
    from src.analysis.models import ATRReading
    ctx = PipelineContext(
        signal_id=signal_id, timeframe=Timeframe.H1,
        bars=_make_bars_dict(), now_utc=_TS,
        spread_usd=0.30, news_events=[], mode="live",
    )
    ctx.entry_signal = EntrySignal(
        direction=Direction.LONG, confidence=0.80,
        entry_zone_top=2005.0, entry_zone_bottom=2000.0,
        reason="BOS bullish", signal_type=SignalType.BOS_BULLISH, timestamp=_TS,
    )
    ctx.filter_result = TradeGateResult(
        signal_id=signal_id, final_result=FilterResult.ALLOWED,
        decisions=[], evaluated_at=_TS,
    )
    ctx.risk_calc = RiskCalculation(
        lot_size=0.10, sl_price=1975.0, tp1_price=2042.5, tp2_price=2080.0,
        sl_distance=25.0, risk_amount_usd=100.0, in_recovery=False, reason="pipeline_calc",
    )
    return ctx


def _blocked_ctx(signal_id: str = "test-002") -> PipelineContext:
    ctx = PipelineContext(
        signal_id=signal_id, timeframe=Timeframe.H1,
        bars=_make_bars_dict(), now_utc=_TS,
        spread_usd=0.30, news_events=[], mode="live",
    )
    ctx.entry_signal = EntrySignal(
        direction=Direction.LONG, confidence=0.80,
        entry_zone_top=2005.0, entry_zone_bottom=2000.0,
        reason="BOS bullish", signal_type=SignalType.BOS_BULLISH, timestamp=_TS,
    )
    ctx.filter_result = TradeGateResult(
        signal_id=signal_id, final_result=FilterResult.BLOCKED,
        decisions=[FilterDecision(
            filter_name="volatility", result=FilterResult.BLOCKED,
            reason="extreme volatility", metric_value=6.0, timestamp=_TS,
        )],
        evaluated_at=_TS,
    )
    return ctx


def _make_audit_entry(action: str = "ORDER_PLACED") -> TradeAuditEntry:
    return TradeAuditEntry(
        audit_id="audit-001",
        timestamp_utc=_TS.isoformat(),
        action_type=AuditAction.ORDER_PLACED if action == "ORDER_PLACED" else AuditAction.ORDER_REJECTED,
        signal_id="test-001",
    )


# ── Test 1: _startup() connects broker and warms up ATR for all 4 TFs ─────────

class TestStartup:
    def test_startup_connects_broker_and_refreshes_atr_for_all_timeframes(self):
        """_startup() must call broker.connect() and ATRService.refresh × 4."""
        orch = _make_orchestrator()
        fake_rates = _fake_rates()

        mock_account = MagicMock()
        mock_account.equity = 10000.0

        with patch("src.orchestrator.strategy_orchestrator.mt5") as mock_mt5:
            mock_mt5.copy_rates_from_pos.return_value = fake_rates
            mock_mt5.account_info.return_value = mock_account

            orch._startup()

        orch._broker.connect.assert_called_once()
        assert orch._atr_service.refresh.call_count == len(Timeframe)
        # One call per timeframe
        called_tfs = {c.args[0] for c in orch._atr_service.refresh.call_args_list}
        assert called_tfs == set(Timeframe)


# ── Test 2: ALLOWED signal → execute_signal called once ───────────────────────

class TestOnNewBarAllowed:
    def test_execute_signal_called_once_for_allowed_signal(self):
        """_on_new_bar() with ALLOWED pipeline result → execute_signal called exactly once."""
        orch = _make_orchestrator()
        allowed_ctx = _allowed_ctx()
        orch._execution_engine.execute_signal.return_value = _make_audit_entry("ORDER_PLACED")

        mock_tick = MagicMock()
        mock_tick.ask = 2005.35
        mock_tick.bid = 2005.00
        mock_tick.last = 2005.00
        mock_account = MagicMock()
        mock_account.equity = 10000.0

        with patch("src.orchestrator.strategy_orchestrator.mt5") as mock_mt5, \
             patch("src.orchestrator.strategy_orchestrator.run_pipeline", return_value=allowed_ctx):
            mock_mt5.symbol_info_tick.return_value = mock_tick
            mock_mt5.account_info.return_value = mock_account

            orch._on_new_bar(_make_bars_dict(), _TS)

        orch._execution_engine.execute_signal.assert_called_once()
        orch._execution_engine.manage_open_positions.assert_called_once()


# ── Test 3: BLOCKED signal → execute_signal NOT called ────────────────────────

class TestOnNewBarBlocked:
    def test_execute_signal_not_called_for_blocked_signal(self):
        """_on_new_bar() with BLOCKED pipeline result → execute_signal must not be called."""
        orch = _make_orchestrator()
        blocked_ctx = _blocked_ctx()

        mock_tick = MagicMock()
        mock_tick.ask = 2005.35
        mock_tick.bid = 2005.00
        mock_tick.last = 2005.00
        mock_account = MagicMock()
        mock_account.equity = 10000.0

        with patch("src.orchestrator.strategy_orchestrator.mt5") as mock_mt5, \
             patch("src.orchestrator.strategy_orchestrator.run_pipeline", return_value=blocked_ctx):
            mock_mt5.symbol_info_tick.return_value = mock_tick
            mock_mt5.account_info.return_value = mock_account

            orch._on_new_bar(_make_bars_dict(), _TS)

        orch._execution_engine.execute_signal.assert_not_called()
        # manage_open_positions always called
        orch._execution_engine.manage_open_positions.assert_called_once()


# ── Test 4: Kill switch active → execute_signal skipped, positions managed ────

class TestKillSwitchActive:
    def test_kill_switch_blocks_entry_but_positions_still_managed(self, tmp_path):
        """Kill switch active → execute_signal skipped; manage_open_positions still called."""
        ks_path = tmp_path / "kill_switch.json"
        orch = _make_orchestrator(kill_switch_path=ks_path)
        allowed_ctx = _allowed_ctx()

        mock_tick = MagicMock()
        mock_tick.ask = 2005.35
        mock_tick.bid = 2005.00
        mock_tick.last = 2005.00
        mock_account = MagicMock()
        mock_account.equity = 10000.0

        with patch("src.orchestrator.strategy_orchestrator.mt5") as mock_mt5, \
             patch("src.orchestrator.strategy_orchestrator.run_pipeline", return_value=allowed_ctx), \
             patch("src.orchestrator.strategy_orchestrator.is_kill_switch_active", return_value=True):
            mock_mt5.symbol_info_tick.return_value = mock_tick
            mock_mt5.account_info.return_value = mock_account

            orch._on_new_bar(_make_bars_dict(), _TS)

        orch._execution_engine.execute_signal.assert_not_called()
        orch._execution_engine.manage_open_positions.assert_called_once()


# ── Test 5: MT5ConnectionError → retry + SystemExit on exhaustion ─────────────

class TestReconnectionExhausted:
    def test_systemExit_raised_after_max_reconnect_retries_exhausted(self):
        """poll_for_new_bar always raises MT5ConnectionError → retries N times → SystemExit."""
        orch = _make_orchestrator()
        max_retries = _CONFIG["orchestrator"]["max_reconnect_retries"]

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return False, _TS, {}   # startup poll (no new bar)
            raise MT5ConnectionError("disconnected")

        with patch("src.orchestrator.strategy_orchestrator.time.sleep"), \
             patch("src.orchestrator.strategy_orchestrator.poll_for_new_bar",
                   side_effect=side_effect), \
             patch.object(orch, "_startup"), \
             patch.object(orch, "_shutdown"):

            # Connect always fails in _reconnect
            orch._broker.connect.return_value = False

            with pytest.raises(SystemExit):
                orch.run()

        # Broker.connect called max_retries times inside _reconnect
        assert orch._broker.connect.call_count == max_retries
