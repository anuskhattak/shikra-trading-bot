"""Unit tests for position_manager.py — T018 (Phase 6, US2) + T022 (Phase 7, US3)."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from src.engine.models import Direction
from src.execution.models import AuditAction, PositionState, TradeAuditEntry
from src.execution.position_manager import (
    _apply_sl_modification,
    apply_partial_close,
    evaluate_trailing_stop,
    manage_positions,
    reconcile_positions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _long_pos(
    ticket: int = 11111,
    entry: float = 1800.0,
    sl: float = 1780.0,
    tp1: float = 1840.0,
    tp2: float = 1860.0,
    trailing_activated: bool = False,
    partial_close_done: bool = False,
    lot_size: float = 0.05,
    signal_id: str = "sig-001",
) -> PositionState:
    return PositionState(
        ticket_id=ticket,
        direction=Direction.LONG,
        entry_price=entry,
        current_sl=sl,
        tp1_price=tp1,
        tp2_price=tp2,
        lot_size=lot_size,
        trailing_activated=trailing_activated,
        partial_close_done=partial_close_done,
        signal_id=signal_id,
    )


def _short_pos(
    ticket: int = 22222,
    entry: float = 1800.0,
    sl: float = 1820.0,
    tp1: float = 1760.0,
    tp2: float = 1740.0,
    trailing_activated: bool = False,
    partial_close_done: bool = False,
    lot_size: float = 0.05,
    signal_id: str = "sig-002",
) -> PositionState:
    return PositionState(
        ticket_id=ticket,
        direction=Direction.SHORT,
        entry_price=entry,
        current_sl=sl,
        tp1_price=tp1,
        tp2_price=tp2,
        lot_size=lot_size,
        trailing_activated=trailing_activated,
        partial_close_done=partial_close_done,
        signal_id=signal_id,
    )


def _cfg(activation: float = 30.0, distance: float = 20.0) -> dict:
    return {"activation_distance": activation, "trailing_distance": distance}


def _full_cfg(
    tp1_close_ratio: float = 0.5,
    activation: float = 30.0,
    distance: float = 20.0,
    slippage_points: int = 5,
    magic_number: int = 0,
) -> dict:
    return {
        "tp1_close_ratio": tp1_close_ratio,
        "activation_distance": activation,
        "trailing_distance": distance,
        "slippage_points": slippage_points,
        "magic_number": magic_number,
    }


def _mock_mt5_constants(mock_mt5) -> None:
    """Assign all MT5 constant attributes used by position_manager."""
    mock_mt5.TRADE_RETCODE_DONE = 10009
    mock_mt5.TRADE_ACTION_DEAL = 1
    mock_mt5.TRADE_ACTION_SLTP = 6
    mock_mt5.ORDER_TYPE_BUY = 0
    mock_mt5.ORDER_TYPE_SELL = 1
    mock_mt5.ORDER_TIME_GTC = 1
    mock_mt5.ORDER_FILLING_IOC = 2


# ---------------------------------------------------------------------------
# T018 — evaluate_trailing_stop: LONG direction
# ---------------------------------------------------------------------------

class TestEvalTrailingLong:
    def test_below_threshold_no_change(self):
        """Price not yet at activation distance — SL must not move."""
        pos = _long_pos(entry=1800.0, sl=1780.0)
        # 1829 < 1800 + 30 = 1830 → not activated
        updated, entry = evaluate_trailing_stop(pos, 1829.0, _cfg())
        assert updated.current_sl == 1780.0
        assert entry is None

    def test_exactly_at_threshold_activates(self):
        """Edge: price == entry + activation_distance → should activate."""
        pos = _long_pos(entry=1800.0, sl=1780.0)
        updated, entry = evaluate_trailing_stop(pos, 1830.0, _cfg())
        assert updated.current_sl == 1830.0 - 20.0  # 1810.0
        assert updated.trailing_activated is True
        assert entry is not None

    def test_above_threshold_activates_and_updates_sl(self):
        pos = _long_pos(entry=1800.0, sl=1780.0)
        updated, entry = evaluate_trailing_stop(pos, 1850.0, _cfg())
        assert updated.current_sl == 1850.0 - 20.0  # 1830.0
        assert entry.action_type == AuditAction.TRAILING_STOP_UPDATED
        assert entry.new_sl_price == 1830.0

    def test_unidirectional_retrace_no_update(self):
        """SL must never move back down for LONG — FR-009 unidirectional invariant."""
        pos = _long_pos(entry=1800.0, sl=1811.0, trailing_activated=True)
        # Retrace: new_sl = 1829 - 20 = 1809 < 1811 → no update
        updated, entry = evaluate_trailing_stop(pos, 1829.0, _cfg())
        assert updated.current_sl == 1811.0
        assert entry is None

    def test_equal_to_current_sl_no_update(self):
        """new_sl == current_sl → no update (strictly greater required)."""
        pos = _long_pos(entry=1800.0, sl=1810.0, trailing_activated=True)
        # Price: 1830 → new_sl = 1830 - 20 = 1810 == 1810 → no move
        updated, entry = evaluate_trailing_stop(pos, 1830.0, _cfg())
        assert updated.current_sl == 1810.0
        assert entry is None

    def test_continued_advance_keeps_trailing(self):
        """After first update, further price advance continues to trail SL up."""
        pos = _long_pos(entry=1800.0, sl=1811.0, trailing_activated=True)
        # new_sl = 1850 - 20 = 1830 > 1811 → apply
        updated, entry = evaluate_trailing_stop(pos, 1850.0, _cfg())
        assert updated.current_sl == 1830.0
        assert entry is not None

    def test_audit_entry_fields(self):
        pos = _long_pos(ticket=99, entry=1800.0, sl=1780.0, signal_id="my-signal")
        _, entry = evaluate_trailing_stop(pos, 1850.0, _cfg())
        assert entry.ticket_id == 99
        assert entry.signal_id == "my-signal"
        assert entry.direction == Direction.LONG.value

    def test_original_position_not_mutated(self):
        """evaluate_trailing_stop must return new PositionState — no in-place mutation."""
        pos = _long_pos(entry=1800.0, sl=1780.0)
        original_sl = pos.current_sl
        evaluate_trailing_stop(pos, 1850.0, _cfg())
        assert pos.current_sl == original_sl  # original unchanged


# ---------------------------------------------------------------------------
# T018 — evaluate_trailing_stop: SHORT direction
# ---------------------------------------------------------------------------

class TestEvalTrailingShort:
    def test_above_threshold_no_change(self):
        """Price not yet at activation distance below entry — no change."""
        pos = _short_pos(entry=1800.0, sl=1820.0)
        # 1771 > 1800 - 30 = 1770 → not activated
        updated, entry = evaluate_trailing_stop(pos, 1771.0, _cfg())
        assert updated.current_sl == 1820.0
        assert entry is None

    def test_exactly_at_threshold_activates(self):
        """Edge: price == entry - activation_distance → should activate."""
        pos = _short_pos(entry=1800.0, sl=1820.0)
        updated, entry = evaluate_trailing_stop(pos, 1770.0, _cfg())
        assert updated.current_sl == 1770.0 + 20.0  # 1790.0
        assert updated.trailing_activated is True
        assert entry.action_type == AuditAction.TRAILING_STOP_UPDATED
        assert entry.new_sl_price == 1790.0

    def test_unidirectional_retrace_no_update(self):
        """SL must never move back up for SHORT — FR-009 unidirectional invariant."""
        pos = _short_pos(entry=1800.0, sl=1789.0, trailing_activated=True)
        # Price retraces up: new_sl = 1771 + 20 = 1791 > 1789 → no update (SL would rise)
        updated, entry = evaluate_trailing_stop(pos, 1771.0, _cfg())
        assert updated.current_sl == 1789.0
        assert entry is None

    def test_continued_drop_updates_sl_downward(self):
        """Further price drop continues to lower SL."""
        pos = _short_pos(entry=1800.0, sl=1789.0, trailing_activated=True)
        # new_sl = 1750 + 20 = 1770 < 1789 → apply
        updated, entry = evaluate_trailing_stop(pos, 1750.0, _cfg())
        assert updated.current_sl == 1770.0
        assert entry is not None

    def test_symmetric_audit_entry(self):
        pos = _short_pos(ticket=77, signal_id="short-sig")
        _, entry = evaluate_trailing_stop(pos, 1750.0, _cfg())
        assert entry.ticket_id == 77
        assert entry.signal_id == "short-sig"
        assert entry.direction == Direction.SHORT.value


# ---------------------------------------------------------------------------
# T018 — _apply_sl_modification
# ---------------------------------------------------------------------------

class TestApplySlModification:
    @patch("src.execution.position_manager.mt5")
    def test_success_on_first_attempt(self, mock_mt5):
        """Broker accepts SL modification on first try — returns (True, "")."""
        mock_mt5.TRADE_RETCODE_DONE = 10009
        mock_mt5.TRADE_ACTION_SLTP = 6
        result = MagicMock()
        result.retcode = 10009
        mock_mt5.order_send.return_value = result

        ok, reason = _apply_sl_modification(12345, 1810.0, 1860.0)

        assert ok
        assert reason == ""
        assert mock_mt5.order_send.call_count == 1

    @patch("src.execution.position_manager.mt5")
    def test_success_on_retry(self, mock_mt5):
        """First attempt fails, second succeeds — returns (True, "") after retry."""
        mock_mt5.TRADE_RETCODE_DONE = 10009
        mock_mt5.TRADE_ACTION_SLTP = 6
        fail_result = MagicMock()
        fail_result.retcode = 10004
        ok_result = MagicMock()
        ok_result.retcode = 10009
        mock_mt5.order_send.side_effect = [fail_result, ok_result]

        ok, _ = _apply_sl_modification(12345, 1810.0, 1860.0)

        assert ok
        assert mock_mt5.order_send.call_count == 2

    @patch("src.execution.position_manager.mt5")
    def test_double_failure_returns_false(self, mock_mt5, monkeypatch):
        """Both attempts fail — returns (False, reason) — US2 S4."""
        mock_mt5.TRADE_RETCODE_DONE = 10009
        mock_mt5.TRADE_ACTION_SLTP = 6
        fail_result = MagicMock()
        fail_result.retcode = 10004
        mock_mt5.order_send.return_value = fail_result
        monkeypatch.setattr(
            "src.execution.position_manager.write_audit_entry", lambda e: None
        )

        ok, reason = _apply_sl_modification(12345, 1810.0, 1860.0)

        assert not ok
        assert "10004" in reason

    @patch("src.execution.position_manager.mt5")
    def test_double_failure_writes_sl_modification_failed_entry(self, mock_mt5):
        """SL_MODIFICATION_FAILED audit entry written after both attempts fail (US2 S4)."""
        mock_mt5.TRADE_RETCODE_DONE = 10009
        mock_mt5.TRADE_ACTION_SLTP = 6
        fail_result = MagicMock()
        fail_result.retcode = 10004
        mock_mt5.order_send.return_value = fail_result

        captured: list[TradeAuditEntry] = []
        with patch(
            "src.execution.position_manager.write_audit_entry",
            side_effect=captured.append,
        ):
            _apply_sl_modification(12345, 1810.0, 1860.0, signal_id="sig-abc")

        assert len(captured) == 1
        entry = captured[0]
        assert entry.action_type == AuditAction.SL_MODIFICATION_FAILED
        assert entry.ticket_id == 12345
        assert entry.new_sl_price == 1810.0
        assert entry.signal_id == "sig-abc"
        assert entry.rejection_reason is not None

    @patch("src.execution.position_manager.mt5")
    def test_order_send_none_treated_as_failure(self, mock_mt5, monkeypatch):
        """mt5.order_send() returning None is handled as failure — no AttributeError."""
        mock_mt5.TRADE_RETCODE_DONE = 10009
        mock_mt5.TRADE_ACTION_SLTP = 6
        mock_mt5.order_send.return_value = None
        monkeypatch.setattr(
            "src.execution.position_manager.write_audit_entry", lambda e: None
        )

        ok, reason = _apply_sl_modification(12345, 1810.0, 1860.0)

        assert not ok
        assert "no response" in reason
        assert mock_mt5.order_send.call_count == 2

    @patch("src.execution.position_manager.mt5")
    def test_exactly_one_retry_no_more(self, mock_mt5, monkeypatch):
        """Retry exactly once — total 2 calls to order_send, never 3+."""
        mock_mt5.TRADE_RETCODE_DONE = 10009
        mock_mt5.TRADE_ACTION_SLTP = 6
        fail_result = MagicMock()
        fail_result.retcode = 10004
        mock_mt5.order_send.return_value = fail_result
        monkeypatch.setattr(
            "src.execution.position_manager.write_audit_entry", lambda e: None
        )

        _apply_sl_modification(99999, 1810.0, 1860.0)

        assert mock_mt5.order_send.call_count == 2


# ---------------------------------------------------------------------------
# T022 — apply_partial_close (US3)
# ---------------------------------------------------------------------------

class TestApplyPartialClose:
    def _ok_result(self, price: float = 1840.0):
        r = MagicMock()
        r.retcode = 10009
        r.price = price
        return r

    def _fail_result(self):
        r = MagicMock()
        r.retcode = 10004
        return r

    def _tick(self, bid: float = 1840.0, ask: float = 1841.0):
        t = MagicMock()
        t.bid = bid
        t.ask = ask
        return t

    @patch("src.execution.position_manager.mt5")
    def test_lot_ratio_applied_and_lot_reduced(self, mock_mt5):
        """50% close ratio on 0.10 lot → closes 0.05, remaining 0.05."""
        _mock_mt5_constants(mock_mt5)
        mock_mt5.symbol_info_tick.return_value = self._tick()
        mock_mt5.order_send.return_value = self._ok_result()

        pos = _long_pos(lot_size=0.10, tp1=1840.0, tp2=1860.0)
        updated, _ = apply_partial_close(pos, _full_cfg(tp1_close_ratio=0.5))

        assert updated.lot_size == 0.05
        assert updated.partial_close_done is True

    @patch("src.execution.position_manager.mt5")
    def test_close_lots_rounded_to_two_decimals(self, mock_mt5):
        """0.10 lot * 0.33 ratio = 0.033 → rounded to 0.03 before broker submission."""
        _mock_mt5_constants(mock_mt5)
        mock_mt5.symbol_info_tick.return_value = self._tick()
        mock_mt5.order_send.return_value = self._ok_result()

        pos = _long_pos(lot_size=0.10, tp1=1840.0, tp2=1860.0)
        apply_partial_close(pos, _full_cfg(tp1_close_ratio=0.33))

        sent_volume = mock_mt5.order_send.call_args_list[0][0][0]["volume"]
        assert sent_volume == 0.03  # round(0.10 * 0.33, 2)

    @patch("src.execution.position_manager.mt5")
    def test_breakeven_sl_set_on_success(self, mock_mt5):
        """Successful partial close moves current_sl to entry_price (BREAKEVEN_SET)."""
        _mock_mt5_constants(mock_mt5)
        mock_mt5.symbol_info_tick.return_value = self._tick()
        mock_mt5.order_send.return_value = self._ok_result()

        pos = _long_pos(entry=1800.0, sl=1780.0, lot_size=0.10, tp1=1840.0, tp2=1860.0)
        updated, _ = apply_partial_close(pos, _full_cfg())

        assert updated.current_sl == 1800.0  # entry_price

    @patch("src.execution.position_manager.mt5")
    def test_returns_partial_close_and_breakeven_entries(self, mock_mt5):
        """Successful partial close returns PARTIAL_CLOSE then BREAKEVEN_SET entries."""
        _mock_mt5_constants(mock_mt5)
        mock_mt5.symbol_info_tick.return_value = self._tick()
        mock_mt5.order_send.return_value = self._ok_result()

        pos = _long_pos(lot_size=0.10)
        _, entries = apply_partial_close(pos, _full_cfg())

        action_types = [e.action_type for e in entries]
        assert AuditAction.PARTIAL_CLOSE in action_types
        assert AuditAction.BREAKEVEN_SET in action_types

    @patch("src.execution.position_manager.mt5")
    def test_broker_failure_returns_unchanged_state(self, mock_mt5):
        """Broker rejection → original PositionState returned unchanged, empty entries."""
        _mock_mt5_constants(mock_mt5)
        mock_mt5.symbol_info_tick.return_value = self._tick()
        mock_mt5.order_send.return_value = self._fail_result()

        pos = _long_pos(lot_size=0.10, partial_close_done=False)
        with patch("src.execution.position_manager.write_audit_entry"):
            updated, entries = apply_partial_close(pos, _full_cfg())

        assert updated is pos
        assert entries == []
        assert updated.partial_close_done is False

    @patch("src.execution.position_manager.mt5")
    def test_close_lots_exceeds_position_clamped_no_crash(self, mock_mt5):
        """close_lots > lot_size (ratio > 1) → clamped to lot_size, logs warning, no crash."""
        _mock_mt5_constants(mock_mt5)
        mock_mt5.symbol_info_tick.return_value = self._tick()
        mock_mt5.order_send.return_value = self._ok_result()

        # ratio=2.0 → close_lots = round(0.01 * 2.0, 2) = 0.02 > lot_size=0.01 → clamped
        pos = _long_pos(lot_size=0.01)
        apply_partial_close(pos, _full_cfg(tp1_close_ratio=2.0))

        sent_volume = mock_mt5.order_send.call_args_list[0][0][0]["volume"]
        assert sent_volume == 0.01  # clamped to lot_size


# ---------------------------------------------------------------------------
# T022 — reconcile_positions (US3)
# ---------------------------------------------------------------------------

class TestReconcilePositions:
    @patch("src.execution.position_manager.mt5")
    def test_absent_ticket_pruned_and_externally_closed_written(self, mock_mt5):
        """Ticket in dict absent from broker → removed + POSITION_EXTERNALLY_CLOSED entry."""
        other = MagicMock()
        other.ticket = 99999
        mock_mt5.positions_get.return_value = [other]

        pos = _long_pos(ticket=11111)
        pruned, entries = reconcile_positions({11111: pos})

        assert 11111 not in pruned
        assert len(entries) == 1
        assert entries[0].action_type == AuditAction.POSITION_EXTERNALLY_CLOSED
        assert entries[0].ticket_id == 11111

    @patch("src.execution.position_manager.mt5")
    def test_present_ticket_unchanged_no_entries(self, mock_mt5):
        """Ticket present in broker response → kept in dict, no audit entries produced."""
        broker_pos = MagicMock()
        broker_pos.ticket = 11111
        mock_mt5.positions_get.return_value = [broker_pos]

        pos = _long_pos(ticket=11111)
        pruned, entries = reconcile_positions({11111: pos})

        assert 11111 in pruned
        assert entries == []

    @patch("src.execution.position_manager.mt5")
    def test_mt5_none_response_skips_reconciliation(self, mock_mt5):
        """mt5.positions_get() returns None → original dict returned unchanged, no entries."""
        mock_mt5.positions_get.return_value = None

        pos = _long_pos(ticket=11111)
        positions = {11111: pos}
        pruned, entries = reconcile_positions(positions)

        assert pruned is positions
        assert entries == []


# ---------------------------------------------------------------------------
# T022 — manage_positions (US3)
# ---------------------------------------------------------------------------

class TestManagePositions:
    @patch("src.execution.position_manager.mt5")
    def test_tp2_hit_removes_position_from_dict(self, mock_mt5):
        """Price >= TP2 → FULL_CLOSE sent → ticket removed from returned dict."""
        _mock_mt5_constants(mock_mt5)
        broker_pos = MagicMock()
        broker_pos.ticket = 11111
        mock_mt5.positions_get.return_value = [broker_pos]
        ok = MagicMock()
        ok.retcode = 10009
        ok.price = 1860.0
        mock_mt5.order_send.return_value = ok

        pos = _long_pos(ticket=11111, entry=1800.0, tp1=1840.0, tp2=1860.0)
        updated_positions, entries = manage_positions({11111: pos}, 1860.0, _full_cfg())

        assert 11111 not in updated_positions
        fc = [e for e in entries if e.action_type == AuditAction.FULL_CLOSE]
        assert len(fc) == 1

    @patch("src.execution.position_manager.mt5")
    def test_tp2_hit_no_trailing_evaluated_on_same_bar(self, mock_mt5):
        """TP2 hit → full close then continue; TRAILING_STOP_UPDATED must NOT appear (D-006)."""
        _mock_mt5_constants(mock_mt5)
        broker_pos = MagicMock()
        broker_pos.ticket = 11111
        mock_mt5.positions_get.return_value = [broker_pos]
        ok = MagicMock()
        ok.retcode = 10009
        ok.price = 1870.0
        mock_mt5.order_send.return_value = ok

        # activation_distance=30 → threshold=1830; price=1870 satisfies both TP2 and trailing
        pos = _long_pos(ticket=11111, entry=1800.0, tp1=1840.0, tp2=1860.0)
        _, entries = manage_positions({11111: pos}, 1870.0, _full_cfg(activation=30.0))

        action_types = [e.action_type for e in entries]
        assert AuditAction.FULL_CLOSE in action_types
        assert AuditAction.TRAILING_STOP_UPDATED not in action_types

    @patch("src.execution.position_manager.mt5")
    def test_tp1_hit_triggers_partial_close(self, mock_mt5):
        """Price >= TP1 and partial_close_done=False → apply_partial_close() applied."""
        _mock_mt5_constants(mock_mt5)
        broker_pos = MagicMock()
        broker_pos.ticket = 11111
        mock_mt5.positions_get.return_value = [broker_pos]
        tick = MagicMock()
        tick.bid = 1840.0
        mock_mt5.symbol_info_tick.return_value = tick
        ok = MagicMock()
        ok.retcode = 10009
        ok.price = 1840.0
        mock_mt5.order_send.return_value = ok

        # activation_distance=100 keeps trailing dormant so only TP1 fires
        pos = _long_pos(
            ticket=11111, entry=1800.0, tp1=1840.0, tp2=1900.0,
            lot_size=0.10, partial_close_done=False,
        )
        updated_positions, entries = manage_positions(
            {11111: pos}, 1840.0, _full_cfg(activation=100.0)
        )

        assert 11111 in updated_positions
        assert updated_positions[11111].partial_close_done is True
        pc = [e for e in entries if e.action_type == AuditAction.PARTIAL_CLOSE]
        assert len(pc) == 1
