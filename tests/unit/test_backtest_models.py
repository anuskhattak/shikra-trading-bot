"""Unit tests for src/backtest/models.py — spec009 T014."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.backtest.models import BacktestResult, SimulatedPosition, TradeRecord
from src.engine.models import Direction

_TS = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)


# ── Test 1 ────────────────────────────────────────────────────────────────────

class TestSimulatedPositionDefaults:
    def test_defaults_are_correct(self):
        """is_tp1_hit and is_closed must default to False; pip_value_per_lot to 10.0."""
        pos = SimulatedPosition(
            signal_id="s1",
            direction=Direction.LONG,
            entry_price=2000.0,
            sl_price=1970.0,
            tp1_price=2045.0,
            tp2_price=2090.0,
            lot_size=0.10,
            opened_at=_TS,
            entry_signal_type="BOS_BULLISH",
            entry_confidence=0.75,
        )
        assert pos.is_tp1_hit is False
        assert pos.is_closed is False
        assert pos.pip_value_per_lot == 10.0


# ── Test 2 ────────────────────────────────────────────────────────────────────

class TestSimulatedPositionAllFields:
    def test_all_fields_stored_correctly(self):
        """All explicitly-set fields must be accessible after construction."""
        pos = SimulatedPosition(
            signal_id="s2",
            direction=Direction.SHORT,
            entry_price=2050.0,
            sl_price=2080.0,
            tp1_price=2020.0,
            tp2_price=1990.0,
            lot_size=0.20,
            opened_at=_TS,
            entry_signal_type="BOS_BEARISH",
            entry_confidence=0.82,
            pip_value_per_lot=100.0,
            is_tp1_hit=True,
            is_closed=False,
        )
        assert pos.direction    == Direction.SHORT
        assert pos.pip_value_per_lot == 100.0
        assert pos.is_tp1_hit   is True
        assert pos.is_closed    is False


# ── Test 3 ────────────────────────────────────────────────────────────────────

class TestTradeRecordDirectionEnum:
    def test_direction_is_direction_enum_not_string(self):
        """TradeRecord.direction must be a Direction enum instance — never a raw string."""
        rec = TradeRecord(
            signal_id="t1",
            direction=Direction.LONG,
            entry_price=2000.0,
            exit_price=2045.0,
            exit_type="TP1",
            pnl_usd=45.0,
            lot_size=0.10,
            opened_at=_TS,
            closed_at=_TS,
            entry_signal_type="BOS_BULLISH",
            entry_confidence=0.75,
        )
        assert isinstance(rec.direction, Direction)
        assert rec.direction == Direction.LONG


# ── Test 4 ────────────────────────────────────────────────────────────────────

class TestDirectionEnumConsistency:
    def test_direction_enum_values_match_engine_models(self):
        """Direction values in backtest models must be identical to src/engine/models.py."""
        from src.engine.models import Direction as EngineDirection

        assert Direction.LONG  == EngineDirection.LONG
        assert Direction.SHORT == EngineDirection.SHORT
        assert Direction.NONE  == EngineDirection.NONE
        # Ensure we're referencing the same class (not a copy)
        assert Direction is EngineDirection


# ── Test 5 ────────────────────────────────────────────────────────────────────

class TestTradeRecordSignalFields:
    def test_entry_signal_type_and_confidence_present(self):
        """TradeRecord must carry entry_signal_type (str) and entry_confidence (float)."""
        rec = TradeRecord(
            signal_id="t2",
            direction=Direction.SHORT,
            entry_price=2050.0,
            exit_price=2080.0,
            exit_type="SL",
            pnl_usd=-300.0,
            lot_size=0.10,
            opened_at=_TS,
            closed_at=_TS,
            entry_signal_type="CHOCH_BEARISH",
            entry_confidence=0.65,
        )
        assert isinstance(rec.entry_signal_type, str)
        assert isinstance(rec.entry_confidence, float)
        assert rec.entry_signal_type == "CHOCH_BEARISH"
        assert rec.entry_confidence  == pytest.approx(0.65)


# ── Test 6 ────────────────────────────────────────────────────────────────────

class TestBacktestResultStructure:
    def test_backtest_result_metrics_defaults_none(self):
        """BacktestResult.metrics must default to None (populated in Phase 5)."""
        result = BacktestResult(trades=[], equity_curve=[10000.0])
        assert result.metrics is None
        assert result.signal_export_path == ""
        assert result.equity_curve == [10000.0]
