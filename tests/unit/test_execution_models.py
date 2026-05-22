"""Unit tests for src/execution/models.py.

Covers: entity instantiation, field defaults, PositionState invariants,
TradeAuditEntry Optional-field contract, all 8 AuditAction values.
"""

from datetime import datetime

import pytest

from src.engine.models import Direction, EntrySignal, SignalType
from src.execution.models import (
    AuditAction,
    ExecutionSignal,
    KillSwitchState,
    OrderTicket,
    PositionState,
    TradeAuditEntry,
)
from src.risk.models import RiskCalculation


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def entry_signal_long():
    return EntrySignal(
        direction=Direction.LONG,
        confidence=0.75,
        entry_zone_top=1850.0,
        entry_zone_bottom=1840.0,
        reason="BOS + FVG confluence",
        components=["BOS", "FVG"],
        signal_type=SignalType.BOS_BULLISH,
        timestamp=datetime(2026, 5, 20, 10, 0, 0),
    )


@pytest.fixture
def risk_calc_long():
    return RiskCalculation(
        lot_size=0.1,
        sl_price=1820.0,
        tp1_price=1870.0,
        tp2_price=1890.0,
        sl_distance=30.0,
        risk_amount_usd=50.0,
        in_recovery=False,
        reason="2% risk, 1:3 RR",
    )


# ---------------------------------------------------------------------------
# AuditAction enum
# ---------------------------------------------------------------------------

class TestAuditAction:
    def test_exactly_8_values(self):
        assert len(AuditAction) == 8

    def test_all_required_names_present(self):
        names = {a.name for a in AuditAction}
        required = {
            "ORDER_PLACED",
            "ORDER_REJECTED",
            "TRAILING_STOP_UPDATED",
            "BREAKEVEN_SET",
            "PARTIAL_CLOSE",
            "FULL_CLOSE",
            "SL_MODIFICATION_FAILED",
            "POSITION_EXTERNALLY_CLOSED",
        }
        assert names == required

    def test_value_equals_name(self):
        # Each enum value must be its own string name (used in JSON serialisation)
        for action in AuditAction:
            assert action.value == action.name

    def test_all_values_accessible_by_name(self):
        assert AuditAction["ORDER_PLACED"] == AuditAction.ORDER_PLACED
        assert AuditAction["POSITION_EXTERNALLY_CLOSED"] == AuditAction.POSITION_EXTERNALLY_CLOSED


# ---------------------------------------------------------------------------
# ExecutionSignal
# ---------------------------------------------------------------------------

class TestExecutionSignal:
    def test_instantiation(self, entry_signal_long, risk_calc_long):
        sig = ExecutionSignal(
            entry_signal=entry_signal_long,
            risk_calc=risk_calc_long,
            signal_id="uuid-001",
            received_at=datetime(2026, 5, 20, 10, 0, 0),
        )
        assert sig.signal_id == "uuid-001"
        assert sig.risk_calc.lot_size == 0.1

    def test_entry_signal_direction_accessible(self, entry_signal_long, risk_calc_long):
        sig = ExecutionSignal(
            entry_signal=entry_signal_long,
            risk_calc=risk_calc_long,
            signal_id="uuid-002",
            received_at=datetime.utcnow(),
        )
        assert sig.entry_signal.direction == Direction.LONG

    def test_entry_reason_accessible_via_entry_signal(self, entry_signal_long, risk_calc_long):
        sig = ExecutionSignal(
            entry_signal=entry_signal_long,
            risk_calc=risk_calc_long,
            signal_id="uuid-003",
            received_at=datetime.utcnow(),
        )
        assert sig.entry_signal.reason == "BOS + FVG confluence"


# ---------------------------------------------------------------------------
# OrderTicket
# ---------------------------------------------------------------------------

class TestOrderTicket:
    def test_instantiation(self):
        ticket = OrderTicket(
            ticket_id=12345,
            direction=Direction.LONG,
            lot_size=0.1,
            requested_price=1845.0,
            actual_fill_price=1845.5,
            sl_price=1820.0,
            tp_price=1890.0,
            open_time=datetime(2026, 5, 20, 10, 0, 0),
            magic_number=20250519,
        )
        assert ticket.ticket_id == 12345
        assert ticket.direction == Direction.LONG
        assert ticket.actual_fill_price == 1845.5

    def test_short_direction(self):
        ticket = OrderTicket(
            ticket_id=99999,
            direction=Direction.SHORT,
            lot_size=0.2,
            requested_price=1900.0,
            actual_fill_price=1899.8,
            sl_price=1930.0,
            tp_price=1850.0,
            open_time=datetime.utcnow(),
            magic_number=20250519,
        )
        assert ticket.direction == Direction.SHORT


# ---------------------------------------------------------------------------
# PositionState
# ---------------------------------------------------------------------------

class TestPositionState:
    def test_default_flags(self):
        pos = PositionState(
            ticket_id=100,
            direction=Direction.LONG,
            entry_price=1845.0,
            current_sl=1820.0,
            tp1_price=1870.0,
            tp2_price=1890.0,
            lot_size=0.1,
        )
        assert pos.trailing_activated is False
        assert pos.partial_close_done is False
        assert pos.signal_id == ""
        assert isinstance(pos.opened_at, datetime)

    def test_long_sl_is_below_entry(self):
        pos = PositionState(
            ticket_id=101,
            direction=Direction.LONG,
            entry_price=1845.0,
            current_sl=1820.0,
            tp1_price=1870.0,
            tp2_price=1890.0,
            lot_size=0.1,
        )
        assert pos.current_sl < pos.entry_price

    def test_short_sl_is_above_entry(self):
        pos = PositionState(
            ticket_id=102,
            direction=Direction.SHORT,
            entry_price=1845.0,
            current_sl=1875.0,
            tp1_price=1820.0,
            tp2_price=1800.0,
            lot_size=0.1,
        )
        assert pos.current_sl > pos.entry_price

    def test_trailing_activated_can_be_set_true(self):
        pos = PositionState(
            ticket_id=103,
            direction=Direction.LONG,
            entry_price=1845.0,
            current_sl=1860.0,  # Moved up after trailing activation
            tp1_price=1870.0,
            tp2_price=1890.0,
            lot_size=0.1,
            trailing_activated=True,
        )
        assert pos.trailing_activated is True

    def test_breakeven_invariant_sl_equals_entry(self):
        # After partial close: partial_close_done=True implies current_sl == entry_price
        pos = PositionState(
            ticket_id=104,
            direction=Direction.LONG,
            entry_price=1845.0,
            current_sl=1845.0,   # Breakeven SL set
            tp1_price=1870.0,
            tp2_price=1890.0,
            lot_size=0.05,       # Reduced after partial close
            partial_close_done=True,
        )
        assert pos.partial_close_done is True
        assert pos.current_sl == pos.entry_price

    def test_opened_at_defaults_to_utcnow(self):
        before = datetime.utcnow()
        pos = PositionState(
            ticket_id=105,
            direction=Direction.LONG,
            entry_price=1845.0,
            current_sl=1820.0,
            tp1_price=1870.0,
            tp2_price=1890.0,
            lot_size=0.1,
        )
        after = datetime.utcnow()
        assert before <= pos.opened_at <= after

    def test_signal_id_explicitly_set(self):
        pos = PositionState(
            ticket_id=106,
            direction=Direction.LONG,
            entry_price=1845.0,
            current_sl=1820.0,
            tp1_price=1870.0,
            tp2_price=1890.0,
            lot_size=0.1,
            signal_id="sig-abc-123",
        )
        assert pos.signal_id == "sig-abc-123"


# ---------------------------------------------------------------------------
# TradeAuditEntry
# ---------------------------------------------------------------------------

class TestTradeAuditEntry:
    def test_mandatory_fields_only(self):
        entry = TradeAuditEntry(
            audit_id="aud-001",
            timestamp_utc="2026-05-20T10:00:00Z",
            action_type=AuditAction.ORDER_REJECTED,
            signal_id="sig-001",
        )
        assert entry.audit_id == "aud-001"
        assert entry.timestamp_utc == "2026-05-20T10:00:00Z"
        assert entry.action_type == AuditAction.ORDER_REJECTED
        assert entry.signal_id == "sig-001"

    def test_all_optional_fields_default_to_none(self):
        entry = TradeAuditEntry(
            audit_id="aud-002",
            timestamp_utc="2026-05-20T10:00:00Z",
            action_type=AuditAction.ORDER_REJECTED,
            signal_id="sig-002",
        )
        assert entry.ticket_id is None
        assert entry.direction is None
        assert entry.lot_size is None
        assert entry.requested_entry_price is None
        assert entry.actual_fill_price is None
        assert entry.sl_price is None
        assert entry.tp1_price is None
        assert entry.tp2_price is None
        assert entry.exit_price is None
        assert entry.realised_pnl is None
        assert entry.rejection_reason is None
        assert entry.new_sl_price is None
        assert entry.max_loss_usd is None
        assert entry.entry_reason is None
        assert entry.exit_reason is None

    def test_order_placed_constitution_fields(self):
        entry = TradeAuditEntry(
            audit_id="aud-003",
            timestamp_utc="2026-05-20T10:00:00Z",
            action_type=AuditAction.ORDER_PLACED,
            signal_id="sig-003",
            ticket_id=99999,
            direction="LONG",
            lot_size=0.1,
            requested_entry_price=1845.0,
            actual_fill_price=1845.5,
            sl_price=1820.0,
            tp1_price=1870.0,
            tp2_price=1890.0,
            max_loss_usd=50.0,
            entry_reason="BOS + FVG confluence",
        )
        # CLAUDE.md §Risk First: max_loss_usd must be populated
        assert entry.max_loss_usd == 50.0
        # CLAUDE.md §Auditability: entry_reason must be populated
        assert entry.entry_reason == "BOS + FVG confluence"
        assert entry.ticket_id == 99999

    def test_order_rejected_reason_populated(self):
        entry = TradeAuditEntry(
            audit_id="aud-004",
            timestamp_utc="2026-05-20T10:00:00Z",
            action_type=AuditAction.ORDER_REJECTED,
            signal_id="sig-004",
            rejection_reason="kill-switch active",
        )
        assert entry.rejection_reason == "kill-switch active"
        assert entry.ticket_id is None  # No broker call made

    def test_partial_close_exit_fields(self):
        entry = TradeAuditEntry(
            audit_id="aud-005",
            timestamp_utc="2026-05-20T10:00:00Z",
            action_type=AuditAction.PARTIAL_CLOSE,
            signal_id="sig-005",
            ticket_id=12345,
            exit_price=1870.0,
            realised_pnl=125.0,
            exit_reason="TP1 reached",
        )
        assert entry.exit_price == 1870.0
        assert entry.realised_pnl == 125.0
        assert entry.exit_reason == "TP1 reached"

    def test_trailing_stop_new_sl_field(self):
        entry = TradeAuditEntry(
            audit_id="aud-006",
            timestamp_utc="2026-05-20T10:00:00Z",
            action_type=AuditAction.TRAILING_STOP_UPDATED,
            signal_id="",
            ticket_id=12345,
            new_sl_price=1850.0,
        )
        assert entry.new_sl_price == 1850.0
        assert entry.signal_id == ""  # Position management event — no signal

    def test_position_externally_closed_exit_reason(self):
        entry = TradeAuditEntry(
            audit_id="aud-007",
            timestamp_utc="2026-05-20T10:00:00Z",
            action_type=AuditAction.POSITION_EXTERNALLY_CLOSED,
            signal_id="",
            ticket_id=12345,
            exit_reason="SL hit",
        )
        assert entry.exit_reason == "SL hit"

    def test_all_audit_actions_can_be_used(self):
        for action in AuditAction:
            entry = TradeAuditEntry(
                audit_id=f"aud-{action.name}",
                timestamp_utc="2026-05-20T10:00:00Z",
                action_type=action,
                signal_id="sig-x",
            )
            assert entry.action_type == action

    def test_sl_modification_failed_entry(self):
        entry = TradeAuditEntry(
            audit_id="aud-008",
            timestamp_utc="2026-05-20T10:00:00Z",
            action_type=AuditAction.SL_MODIFICATION_FAILED,
            signal_id="",
            ticket_id=12345,
            rejection_reason="broker returned RETCODE_ERROR",
        )
        assert entry.action_type == AuditAction.SL_MODIFICATION_FAILED
        assert entry.rejection_reason is not None


# ---------------------------------------------------------------------------
# KillSwitchState
# ---------------------------------------------------------------------------

class TestKillSwitchState:
    def test_defaults_to_inactive(self):
        ks = KillSwitchState()
        assert ks.active is False
        assert ks.activated_at is None
        assert ks.activated_by is None

    def test_explicit_activation_fields(self):
        now = datetime(2026, 5, 20, 10, 0, 0)
        ks = KillSwitchState(
            active=True,
            activated_at=now,
            activated_by="operator-terminal",
        )
        assert ks.active is True
        assert ks.activated_at == now
        assert ks.activated_by == "operator-terminal"

    def test_deactivated_state(self):
        ks = KillSwitchState(active=False, activated_at=None, activated_by=None)
        assert ks.active is False
