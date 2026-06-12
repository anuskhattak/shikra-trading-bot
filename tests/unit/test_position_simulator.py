"""Unit tests for src/backtest/position_simulator.py — spec009 T018."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.analysis.models import OHLCVBar
from src.backtest.models import SimulatedPosition
from src.backtest.position_simulator import simulate_bar
from src.engine.models import Direction

_TS  = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
_TS2 = datetime(2026, 1, 15, 11, 0, tzinfo=timezone.utc)


def _long_pos(**overrides) -> SimulatedPosition:
    defaults = dict(
        signal_id="sig-long",
        direction=Direction.LONG,
        entry_price=2000.0,
        sl_price=1970.0,
        tp1_price=2045.0,
        tp2_price=2090.0,
        lot_size=0.10,
        opened_at=_TS,
        entry_signal_type="BOS_BULLISH",
        entry_confidence=0.80,
        pip_value_per_lot=10.0,
    )
    defaults.update(overrides)
    return SimulatedPosition(**defaults)


def _short_pos(**overrides) -> SimulatedPosition:
    defaults = dict(
        signal_id="sig-short",
        direction=Direction.SHORT,
        entry_price=2050.0,
        sl_price=2080.0,
        tp1_price=2020.0,
        tp2_price=1990.0,
        lot_size=0.10,
        opened_at=_TS,
        entry_signal_type="BOS_BEARISH",
        entry_confidence=0.75,
        pip_value_per_lot=10.0,
    )
    defaults.update(overrides)
    return SimulatedPosition(**defaults)


def _bar(low: float = 1990.0, high: float = 2010.0) -> OHLCVBar:
    return OHLCVBar(
        open=2000.0, high=high, low=low, close=2005.0, volume=100.0, timestamp=_TS2
    )


# ── Test 1: already-closed position is a no-op ───────────────────────────────

class TestClosedPositionNoOp:
    def test_closed_position_returns_unchanged_and_no_record(self):
        """simulate_bar on a closed position must return it unchanged with no TradeRecord."""
        pos = _long_pos(is_closed=True)
        updated, record = simulate_bar(pos, _bar())
        assert updated.is_closed is True
        assert record is None


# ── Test 2: SL hit — LONG ─────────────────────────────────────────────────────

class TestSLHitLong:
    def test_sl_triggers_when_bar_low_touches_sl_price(self):
        """LONG position: SL hit when bar.low <= sl_price."""
        pos = _long_pos()
        updated, record = simulate_bar(pos, _bar(low=1969.0, high=2010.0))

        assert updated.is_closed is True
        assert record is not None
        assert record.exit_type  == "SL"
        assert record.exit_price == pytest.approx(1970.0)  # sl_price
        # Loss: direction_sign=+1, (1970-2000)*0.10*10 = -30
        assert record.pnl_usd == pytest.approx(-30.0 * 0.10 * 10.0)
        assert record.direction == Direction.LONG


# ── Test 3: TP1 hit — partial close ──────────────────────────────────────────

class TestTP1Hit:
    def test_tp1_halves_lot_size_and_moves_sl_to_breakeven(self):
        """TP1 hit: lot_size halved, sl moved to entry_price, is_tp1_hit=True, no record."""
        pos = _long_pos()
        updated, record = simulate_bar(pos, _bar(low=1990.0, high=2050.0))  # touches TP1=2045

        assert record is None         # position still open
        assert updated.is_closed is False
        assert updated.is_tp1_hit is True
        assert updated.lot_size == pytest.approx(0.05)        # halved
        assert updated.sl_price == pytest.approx(2000.0)      # moved to entry_price


# ── Test 4: TP2 hit before SL ────────────────────────────────────────────────

class TestTP2HitWithoutSL:
    def test_tp2_closes_full_position_when_sl_not_hit(self):
        """TP2 hit with bar.low safely above SL → position closes at TP2."""
        pos = _long_pos()
        updated, record = simulate_bar(pos, _bar(low=1985.0, high=2095.0))  # SL=1970 NOT hit

        assert updated.is_closed is True
        assert record is not None
        assert record.exit_type  == "TP2"
        assert record.exit_price == pytest.approx(2090.0)
        assert record.pnl_usd    == pytest.approx((2090.0 - 2000.0) * 0.10 * 10.0)


# ── Test 5: same-bar SL + TP2 → SL wins (D-004 conservative rule) ────────────

class TestConservativeRuleSameBothSLAndTP2:
    def test_sl_wins_when_both_sl_and_tp2_triggered_on_same_bar(self):
        """D-004: if bar wicks down to SL AND up to TP2, SL always wins (loss recorded)."""
        pos = _long_pos()
        # bar.low touches SL (1969 <= 1970) AND bar.high touches TP2 (2095 >= 2090)
        both_hit = _bar(low=1969.0, high=2095.0)
        updated, record = simulate_bar(pos, both_hit)

        assert updated.is_closed is True
        assert record is not None
        assert record.exit_type == "SL"                # SL wins
        assert record.pnl_usd   < 0                   # loss, not profit


# ── Test 6: after TP1, TP2 hit ───────────────────────────────────────────────

class TestAfterTP1ThenTP2:
    def test_tp2_closes_remaining_half_after_tp1_hit(self):
        """After TP1 partial close, TP2 hit closes the remaining half-lot."""
        pos = _long_pos(is_tp1_hit=True, sl_price=2000.0, lot_size=0.05)
        # low=2001.0 keeps SL (2000.0) un-triggered; high=2095.0 hits TP2 (2090.0)
        updated, record = simulate_bar(pos, _bar(low=2001.0, high=2095.0))

        assert updated.is_closed is True
        assert record is not None
        assert record.exit_type  == "TP2"
        assert record.lot_size   == pytest.approx(0.05)  # half lot
        assert record.pnl_usd    == pytest.approx((2090.0 - 2000.0) * 0.05 * 10.0)


# ── Test 7: after TP1, breakeven SL hit ──────────────────────────────────────

class TestAfterTP1ThenBreakevenSL:
    def test_breakeven_sl_closes_at_entry_price_zero_pnl(self):
        """After TP1, breakeven SL hit → exit at entry_price (P&L = 0)."""
        pos = _long_pos(is_tp1_hit=True, sl_price=2000.0, lot_size=0.05)
        # bar.low touches breakeven SL (1995 <= 2000), TP2 NOT hit
        updated, record = simulate_bar(pos, _bar(low=1995.0, high=2050.0))

        assert updated.is_closed is True
        assert record is not None
        assert record.exit_type  == "SL"
        assert record.exit_price == pytest.approx(2000.0)   # entry_price = breakeven
        assert record.pnl_usd    == pytest.approx(0.0)      # no P&L at breakeven


# ── Test 8: SHORT direction — SL wins ────────────────────────────────────────

class TestShortDirectionSLWins:
    def test_short_sl_triggers_when_bar_high_reaches_sl_price(self):
        """SHORT: SL triggered when bar.high >= sl_price (2080). SL wins over TP2."""
        pos = _short_pos()
        # bar.high reaches SL (2085 >= 2080) AND bar.low reaches TP2 (1988 <= 1990)
        both_hit = _bar(low=1988.0, high=2085.0)
        updated, record = simulate_bar(pos, both_hit)

        assert updated.is_closed is True
        assert record is not None
        assert record.exit_type == "SL"
        assert record.exit_price == pytest.approx(2080.0)
        # SHORT loss: direction_sign=-1, (-1)*(2080-2050)*0.10*10 = -30
        assert record.pnl_usd == pytest.approx(-30.0 * 0.10 * 10.0)
