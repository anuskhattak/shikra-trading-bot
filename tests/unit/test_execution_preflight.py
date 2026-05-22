"""Unit tests for preflight.py — all 5 pre-flight checks + run_preflight orchestrator (T013)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.engine.models import Direction, EntrySignal
from src.execution.models import ExecutionSignal, PositionState
from src.execution.preflight import (
    check_daily_drawdown,
    check_existing_position,
    check_kill_switch,
    check_margin_sufficiency,
    check_minimum_stop_distance,
    run_preflight,
)
from src.risk.models import RiskCalculation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry_signal(direction: Direction = Direction.LONG) -> EntrySignal:
    return EntrySignal(
        direction=direction,
        confidence=0.8,
        entry_zone_top=1900.0,
        entry_zone_bottom=1895.0,
        reason="BOS + FVG confluence",
    )


def _risk_calc(sl_price: float = 1880.0) -> RiskCalculation:
    return RiskCalculation(
        lot_size=0.05,
        sl_price=sl_price,
        tp1_price=1920.0,
        tp2_price=1940.0,
        sl_distance=abs(1897.5 - sl_price),
        risk_amount_usd=50.0,
        in_recovery=False,
        reason="valid",
    )


def _exec_signal(direction: Direction = Direction.LONG, sl_price: float = 1880.0) -> ExecutionSignal:
    return ExecutionSignal(
        entry_signal=_entry_signal(direction),
        risk_calc=_risk_calc(sl_price),
        signal_id="test-signal-001",
        received_at=datetime.utcnow(),
    )


def _long_position(ticket: int = 12345) -> PositionState:
    return PositionState(
        ticket_id=ticket,
        direction=Direction.LONG,
        entry_price=1900.0,
        current_sl=1880.0,
        tp1_price=1920.0,
        tp2_price=1940.0,
        lot_size=0.05,
    )


def _preflight_config() -> dict:
    return {"risk": {"max_daily_drawdown_pct": 5.0}}


# ---------------------------------------------------------------------------
# T013 — check_kill_switch
# ---------------------------------------------------------------------------

class TestCheckKillSwitch:
    def test_active_returns_false(self, tmp_path):
        from src.execution.kill_switch import activate_kill_switch
        ks_path = tmp_path / "kill_switch.json"
        activate_kill_switch(path=ks_path)

        ok, reason = check_kill_switch(path=ks_path)

        assert not ok
        assert "kill-switch" in reason.lower()

    def test_inactive_file_absent_returns_true(self, tmp_path):
        ks_path = tmp_path / "nonexistent.json"
        ok, reason = check_kill_switch(path=ks_path)
        assert ok
        assert reason == ""

    def test_deactivated_returns_true(self, tmp_path):
        from src.execution.kill_switch import activate_kill_switch, deactivate_kill_switch
        ks_path = tmp_path / "kill_switch.json"
        activate_kill_switch(path=ks_path)
        deactivate_kill_switch(path=ks_path)

        ok, _ = check_kill_switch(path=ks_path)
        assert ok


# ---------------------------------------------------------------------------
# T013 — check_existing_position
# ---------------------------------------------------------------------------

class TestCheckExistingPosition:
    def test_empty_positions_allows(self):
        ok, reason = check_existing_position({}, Direction.LONG)
        assert ok

    def test_same_direction_blocks(self):
        positions = {12345: _long_position()}
        ok, reason = check_existing_position(positions, Direction.LONG)
        assert not ok
        assert "pyramiding" in reason.lower()
        assert "12345" in reason

    def test_opposite_direction_allows(self):
        positions = {12345: _long_position()}
        ok, _ = check_existing_position(positions, Direction.SHORT)
        assert ok

    def test_short_position_blocks_short(self):
        short_pos = PositionState(
            ticket_id=99, direction=Direction.SHORT,
            entry_price=1900.0, current_sl=1920.0,
            tp1_price=1880.0, tp2_price=1860.0, lot_size=0.05,
        )
        ok, reason = check_existing_position({99: short_pos}, Direction.SHORT)
        assert not ok
        assert "short" in reason.lower()


# ---------------------------------------------------------------------------
# T013 — check_daily_drawdown
# ---------------------------------------------------------------------------

class TestCheckDailyDrawdown:
    def test_no_drawdown_allows(self):
        ok, _ = check_daily_drawdown(10000.0, 10000.0, 5.0)
        assert ok

    def test_below_threshold_allows(self):
        ok, _ = check_daily_drawdown(10000.0, 9700.0, 5.0)  # 3% drawdown
        assert ok

    def test_at_threshold_blocks(self):
        ok, reason = check_daily_drawdown(10000.0, 9500.0, 5.0)  # 5% exactly
        assert not ok
        assert "drawdown" in reason.lower()

    def test_above_threshold_blocks(self):
        ok, reason = check_daily_drawdown(10000.0, 9000.0, 5.0)  # 10% drawdown
        assert not ok
        assert "drawdown" in reason.lower()


# ---------------------------------------------------------------------------
# T013 — check_margin_sufficiency
# ---------------------------------------------------------------------------

class TestCheckMarginSufficiency:
    @patch("src.execution.preflight.mt5")
    def test_sufficient_margin_allows(self, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1900.0)
        mock_mt5.TRADE_ACTION_DEAL = 1
        mock_mt5.ORDER_TYPE_BUY = 0
        check_result = MagicMock()
        check_result.retcode = 0
        mock_mt5.order_check.return_value = check_result

        ok, _ = check_margin_sufficiency(0.05)
        assert ok

    @patch("src.execution.preflight.mt5")
    def test_insufficient_margin_blocks(self, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1900.0)
        mock_mt5.TRADE_ACTION_DEAL = 1
        mock_mt5.ORDER_TYPE_BUY = 0
        check_result = MagicMock()
        check_result.retcode = 10019  # TRADE_RETCODE_NO_MONEY
        mock_mt5.order_check.return_value = check_result

        ok, reason = check_margin_sufficiency(0.05)
        assert not ok
        assert "margin" in reason.lower()

    @patch("src.execution.preflight.mt5")
    def test_no_price_data_blocks(self, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = None
        ok, reason = check_margin_sufficiency(0.05)
        assert not ok
        assert "price" in reason.lower()

    @patch("src.execution.preflight.mt5")
    def test_order_check_none_blocks(self, mock_mt5):
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1900.0)
        mock_mt5.TRADE_ACTION_DEAL = 1
        mock_mt5.ORDER_TYPE_BUY = 0
        mock_mt5.order_check.return_value = None

        ok, reason = check_margin_sufficiency(0.05)
        assert not ok
        assert "broker" in reason.lower()


# ---------------------------------------------------------------------------
# T013 — check_minimum_stop_distance
# ---------------------------------------------------------------------------

class TestCheckMinimumStopDistance:
    @patch("src.execution.preflight.mt5")
    def test_sufficient_distance_allows(self, mock_mt5):
        sym = MagicMock()
        sym.point = 0.01
        sym.trade_stops_level = 100  # 100 points minimum
        mock_mt5.symbol_info.return_value = sym

        # |1900 - 1880| / 0.01 = 2000 points > 100
        ok, _ = check_minimum_stop_distance(Direction.LONG, 1900.0, 1880.0)
        assert ok

    @patch("src.execution.preflight.mt5")
    def test_insufficient_distance_blocks(self, mock_mt5):
        sym = MagicMock()
        sym.point = 0.01
        sym.trade_stops_level = 5000  # 5000 points minimum
        mock_mt5.symbol_info.return_value = sym

        # |1900 - 1880| / 0.01 = 2000 points < 5000
        ok, reason = check_minimum_stop_distance(Direction.LONG, 1900.0, 1880.0)
        assert not ok
        assert "minimum" in reason.lower()

    @patch("src.execution.preflight.mt5")
    def test_short_direction_computes_correctly(self, mock_mt5):
        sym = MagicMock()
        sym.point = 0.01
        sym.trade_stops_level = 100
        mock_mt5.symbol_info.return_value = sym

        # SHORT: entry=1900, SL=1920 → |1900 - 1920| / 0.01 = 2000 > 100
        ok, _ = check_minimum_stop_distance(Direction.SHORT, 1900.0, 1920.0)
        assert ok

    @patch("src.execution.preflight.mt5")
    def test_symbol_info_none_blocks(self, mock_mt5):
        mock_mt5.symbol_info.return_value = None
        ok, reason = check_minimum_stop_distance(Direction.LONG, 1900.0, 1880.0)
        assert not ok
        assert "broker" in reason.lower()


# ---------------------------------------------------------------------------
# T013 — run_preflight short-circuit order (D-006)
# ---------------------------------------------------------------------------

class TestRunPreflight:
    def test_all_pass_returns_true(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "src.execution.preflight.check_margin_sufficiency",
            lambda lot_size: (True, ""),
        )
        monkeypatch.setattr(
            "src.execution.preflight.check_minimum_stop_distance",
            lambda *a: (True, ""),
        )
        ks_path = tmp_path / "ks.json"  # absent = inactive
        ok, reason = run_preflight(
            _exec_signal(), {}, 10000.0, 10000.0, _preflight_config(), ks_path
        )
        assert ok
        assert reason == ""

    def test_kill_switch_blocks_without_mt5_calls(self, tmp_path, monkeypatch):
        """Kill-switch short-circuits before any MT5 call (D-006)."""
        from src.execution.kill_switch import activate_kill_switch
        ks_path = tmp_path / "ks.json"
        activate_kill_switch(path=ks_path)

        mt5_called: list[str] = []
        monkeypatch.setattr(
            "src.execution.preflight.check_margin_sufficiency",
            lambda lot_size: mt5_called.append("margin") or (True, ""),
        )
        monkeypatch.setattr(
            "src.execution.preflight.check_minimum_stop_distance",
            lambda *a: mt5_called.append("minstop") or (True, ""),
        )

        ok, reason = run_preflight(
            _exec_signal(), {}, 10000.0, 10000.0, _preflight_config(), ks_path
        )

        assert not ok
        assert "kill-switch" in reason.lower()
        assert mt5_called == [], "No MT5 calls when kill-switch blocks"

    def test_pyramiding_blocks_before_mt5_calls(self, tmp_path, monkeypatch):
        ks_path = tmp_path / "ks.json"  # absent = inactive
        mt5_called: list[str] = []
        monkeypatch.setattr(
            "src.execution.preflight.check_margin_sufficiency",
            lambda lot_size: mt5_called.append("margin") or (True, ""),
        )
        monkeypatch.setattr(
            "src.execution.preflight.check_minimum_stop_distance",
            lambda *a: mt5_called.append("minstop") or (True, ""),
        )

        positions = {12345: _long_position()}
        ok, reason = run_preflight(
            _exec_signal(Direction.LONG), positions, 10000.0, 10000.0, _preflight_config(), ks_path
        )

        assert not ok
        assert "pyramiding" in reason.lower()
        assert mt5_called == [], "No MT5 calls when pyramiding blocks"

    def test_drawdown_rejection(self, tmp_path, monkeypatch):
        """US1 Scenario 2 — daily drawdown reached blocks order."""
        ks_path = tmp_path / "ks.json"
        monkeypatch.setattr("src.execution.preflight.check_margin_sufficiency", lambda l: (True, ""))
        monkeypatch.setattr("src.execution.preflight.check_minimum_stop_distance", lambda *a: (True, ""))

        # 10% drawdown > 5% limit
        ok, reason = run_preflight(
            _exec_signal(), {}, 10000.0, 9000.0, _preflight_config(), ks_path
        )

        assert not ok
        assert "drawdown" in reason.lower()

    def test_margin_rejection(self, tmp_path, monkeypatch):
        """US1 Scenario 3 — insufficient margin blocks order."""
        ks_path = tmp_path / "ks.json"
        monkeypatch.setattr(
            "src.execution.preflight.check_margin_sufficiency",
            lambda l: (False, "insufficient margin"),
        )
        monkeypatch.setattr("src.execution.preflight.check_minimum_stop_distance", lambda *a: (True, ""))

        ok, reason = run_preflight(
            _exec_signal(), {}, 10000.0, 10000.0, _preflight_config(), ks_path
        )

        assert not ok
        assert "margin" in reason.lower()

    def test_min_stop_rejection(self, tmp_path, monkeypatch):
        """US1 Scenario 4 — SL below minimum stop distance blocks order."""
        ks_path = tmp_path / "ks.json"
        monkeypatch.setattr("src.execution.preflight.check_margin_sufficiency", lambda l: (True, ""))
        monkeypatch.setattr(
            "src.execution.preflight.check_minimum_stop_distance",
            lambda *a: (False, "SL distance below minimum"),
        )

        ok, reason = run_preflight(
            _exec_signal(), {}, 10000.0, 10000.0, _preflight_config(), ks_path
        )

        assert not ok
        assert "minimum" in reason.lower() or "below" in reason.lower()

    def test_kill_switch_rejection_us1_scenario(self, tmp_path, monkeypatch):
        """US4 Scenario 1 — kill-switch active → ORDER_REJECTED, no broker call."""
        from src.execution.kill_switch import activate_kill_switch
        ks_path = tmp_path / "ks.json"
        activate_kill_switch(path=ks_path)
        monkeypatch.setattr("src.execution.preflight.check_margin_sufficiency", lambda l: (True, ""))
        monkeypatch.setattr("src.execution.preflight.check_minimum_stop_distance", lambda *a: (True, ""))

        ok, reason = run_preflight(
            _exec_signal(), {}, 10000.0, 10000.0, _preflight_config(), ks_path
        )

        assert not ok
        assert "kill-switch" in reason.lower()
