"""Unit tests for src/orchestrator/pipeline.py — spec009 T007.

5 tests covering all pipeline short-circuit paths:
  1. Full ALLOWED path — risk_calc populated
  2. Filter BLOCKED — risk_calc is None
  3. ATR not ready — entry_signal is None (short-circuit before SMC)
  4. NONE signal — filter not called (short-circuit before filters)
  5. ATR stage exception — graceful return, ctx unchanged
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.analysis.models import ATRReading, OHLCVBar, Timeframe
from src.engine.models import Direction, EntrySignal, SignalType
from src.filters.models import FilterDecision, FilterResult, TradeGateResult
from src.orchestrator.models import PipelineContext
from src.orchestrator.pipeline import run_pipeline


_TS = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

_CONFIG = {
    "risk": {
        "sl_atr_multiplier": 1.5,
        "tp1_rr_ratio": 1.5,
        "tp2_rr_ratio": 3.0,
        "risk_percent": 1.0,
        "pip_value_per_lot": 10.0,
        "max_lot_size": 5.0,
        "min_lot_size": 0.01,
    },
    "analysis": {"atr": {"period": 14, "reference_period": 20}},
    "filters": {
        "spread": {"max_spread_usd": 0.50},
        "news": {"pre_event_minutes": 30, "post_event_minutes": 15, "impact_levels": ["HIGH"]},
        "volatility": {"atr_lookback": 14, "low_atr_ratio": 0.5, "extreme_atr_ratio": 5.0},
        "sessions": {},
    },
}


def _make_bar() -> OHLCVBar:
    return OHLCVBar(open=2000.0, high=2010.0, low=1990.0, close=2005.0, volume=100.0, timestamp=_TS)


def _make_bars(n: int = 60) -> list[OHLCVBar]:
    return [_make_bar() for _ in range(n)]


def _make_ctx(mode: str = "backtest") -> PipelineContext:
    bars = {tf: _make_bars() for tf in Timeframe}
    return PipelineContext(
        signal_id="test-signal-001",
        timeframe=Timeframe.H1,
        bars=bars,
        now_utc=_TS,
        spread_usd=0.30,
        news_events=[],
        mode=mode,
        balance=10000.0,
        current_equity=10000.0,
    )


def _make_atr_reading(tf: Timeframe, current: float = 20.0, reference: float = 15.0) -> ATRReading:
    return ATRReading(
        timeframe=tf, current_atr=current, reference_atr=reference,
        ratio=current / reference, bar_count=60, timestamp=_TS,
    )


def _make_allowed_gate(signal_id: str = "test-signal-001") -> TradeGateResult:
    return TradeGateResult(
        signal_id=signal_id,
        final_result=FilterResult.ALLOWED,
        decisions=[],
        evaluated_at=_TS,
    )


def _make_blocked_gate(signal_id: str = "test-signal-001") -> TradeGateResult:
    return TradeGateResult(
        signal_id=signal_id,
        final_result=FilterResult.BLOCKED,
        decisions=[FilterDecision(
            filter_name="volatility", result=FilterResult.BLOCKED,
            reason="ATR extreme", metric_value=5.5, timestamp=_TS,
        )],
        evaluated_at=_TS,
    )


def _make_long_signal() -> EntrySignal:
    return EntrySignal(
        direction=Direction.LONG,
        confidence=0.80,
        entry_zone_top=2005.0,
        entry_zone_bottom=2000.0,
        reason="BOS bullish + FVG",
        signal_type=SignalType.BOS_BULLISH,
        timestamp=_TS,
    )


def _make_none_signal() -> EntrySignal:
    return EntrySignal(
        direction=Direction.NONE,
        confidence=0.0,
        entry_zone_top=0.0,
        entry_zone_bottom=0.0,
        reason="no signal",
        signal_type=SignalType.NONE,
        timestamp=_TS,
    )


# ── Test 1: Full ALLOWED path ─────────────────────────────────────────────────

class TestFullAllowedPath:
    def test_risk_calc_populated_on_full_allowed_pipeline(self):
        """ATR ready + LONG signal + ALLOWED filter → risk_calc is not None."""
        mock_svc = MagicMock()
        mock_svc.refresh.side_effect = lambda tf, bars: _make_atr_reading(tf)

        with patch("src.orchestrator.pipeline.generate_signal", return_value=_make_long_signal()), \
             patch("src.orchestrator.pipeline.evaluate_filters", return_value=_make_allowed_gate()):

            ctx = run_pipeline(_make_ctx(), mock_svc, _CONFIG)

        # ATR populated for all 4 timeframes
        assert len(ctx.atr_readings) == 4
        # Signal detected
        assert ctx.entry_signal is not None
        assert ctx.entry_signal.direction == Direction.LONG
        # Filter passed
        assert ctx.filter_result is not None
        assert ctx.filter_result.final_result == FilterResult.ALLOWED
        # Risk calc populated with valid lot size
        assert ctx.risk_calc is not None
        assert ctx.risk_calc.lot_size > 0.0
        assert ctx.risk_calc.sl_price < 2002.5   # SL below LONG entry
        assert ctx.risk_calc.tp1_price > 2002.5  # TP1 above entry


# ── Test 2: Filter BLOCKED → risk_calc is None ───────────────────────────────

class TestFilterBlocked:
    def test_risk_calc_is_none_when_filter_blocks(self):
        """BLOCKED filter → risk_calc must be None (short-circuit)."""
        mock_svc = MagicMock()
        mock_svc.refresh.side_effect = lambda tf, bars: _make_atr_reading(tf)

        with patch("src.orchestrator.pipeline.generate_signal", return_value=_make_long_signal()), \
             patch("src.orchestrator.pipeline.evaluate_filters", return_value=_make_blocked_gate()):

            ctx = run_pipeline(_make_ctx(), mock_svc, _CONFIG)

        assert ctx.filter_result is not None
        assert ctx.filter_result.final_result == FilterResult.BLOCKED
        assert ctx.risk_calc is None


# ── Test 3: ATR not ready → entry_signal is None ─────────────────────────────

class TestATRNotReady:
    def test_entry_signal_none_when_atr_not_ready(self):
        """ATR refresh returns None current_atr → short-circuit before SMC stage."""
        mock_svc = MagicMock()
        # Return ATRReading with no data (current_atr=None)
        mock_svc.refresh.side_effect = lambda tf, bars: ATRReading(
            timeframe=tf, current_atr=None, reference_atr=None,
            ratio=None, bar_count=0, timestamp=_TS,
        )

        with patch("src.orchestrator.pipeline.generate_signal") as mock_smc, \
             patch("src.orchestrator.pipeline.evaluate_filters") as mock_filters:

            ctx = run_pipeline(_make_ctx(), mock_svc, _CONFIG)

            # SMC and filters must NOT be called
            mock_smc.assert_not_called()
            mock_filters.assert_not_called()

        assert ctx.entry_signal is None
        assert ctx.filter_result is None
        assert ctx.risk_calc is None


# ── Test 4: NONE signal → filters not called ─────────────────────────────────

class TestNoneSignal:
    def test_filters_not_called_when_signal_is_none(self):
        """direction=NONE → short-circuit before filter evaluation."""
        mock_svc = MagicMock()
        mock_svc.refresh.side_effect = lambda tf, bars: _make_atr_reading(tf)

        with patch("src.orchestrator.pipeline.generate_signal", return_value=_make_none_signal()), \
             patch("src.orchestrator.pipeline.evaluate_filters") as mock_filters:

            ctx = run_pipeline(_make_ctx(), mock_svc, _CONFIG)

            mock_filters.assert_not_called()

        assert ctx.entry_signal is not None
        assert ctx.entry_signal.direction == Direction.NONE
        assert ctx.filter_result is None
        assert ctx.risk_calc is None


# ── Test 5: ATR stage exception → graceful return ─────────────────────────────

class TestATRStageException:
    def test_atr_exception_does_not_raise_and_ctx_is_clean(self):
        """Exception in ATR refresh → run_pipeline returns without raising; ctx has no outputs."""
        mock_svc = MagicMock()
        mock_svc.refresh.side_effect = RuntimeError("MT5 disconnected")

        with patch("src.orchestrator.pipeline.generate_signal") as mock_smc, \
             patch("src.orchestrator.pipeline.evaluate_filters") as mock_filters:

            # Must not raise
            ctx = run_pipeline(_make_ctx(), mock_svc, _CONFIG)

            mock_smc.assert_not_called()
            mock_filters.assert_not_called()

        # atr_readings is empty (refresh raised before any could be stored)
        assert ctx.atr_readings == {}
        assert ctx.entry_signal is None
        assert ctx.filter_result is None
        assert ctx.risk_calc is None
