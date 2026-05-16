"""Unit tests for src/risk/trade_limits.py — spec003 FR-016 to FR-022.

TDD: all tests written BEFORE implementation; they must FAIL until T010 is complete.
Run: pytest tests/unit/test_risk_trade_limits.py
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.risk.trade_limits import (
    is_trade_limit_allowed,
    record_sl_hit,
    record_trade_opened,
    record_trade_won,
)
from src.risk.models import RiskState


def _cfg(
    max_trades_per_day: int = 5,
    max_trades_per_session: int = 2,
    cooldown_after_sl_hours: float = 2.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        max_trades_per_day=max_trades_per_day,
        max_trades_per_session=max_trades_per_session,
        cooldown_after_sl_hours=cooldown_after_sl_hours,
    )


def _state(**kwargs) -> RiskState:
    defaults = dict(
        day_start_equity=10_000.0,
        trades_today=0,
        session_trades={},
        last_sl_time=None,
        consecutive_losses=0,
    )
    defaults.update(kwargs)
    return RiskState(**defaults)


_NOW = datetime(2026, 5, 16, 10, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# T009 — US4: Trade limits (FR-016 to FR-022)
# ---------------------------------------------------------------------------


def test_daily_limit_blocks_when_reached():
    """FR-017: trades_today=5, max=5 → blocked."""
    state = _state(trades_today=5)
    result = is_trade_limit_allowed(state, _cfg(max_trades_per_day=5), _NOW, "LONDON")
    assert result.allowed is False
    assert "daily" in result.reason.lower()


def test_daily_limit_allows_below():
    """FR-017: trades_today=4, max=5 → allowed."""
    state = _state(trades_today=4)
    result = is_trade_limit_allowed(state, _cfg(max_trades_per_day=5), _NOW, "LONDON")
    assert result.allowed is True


def test_session_limit_blocks():
    """FR-018: session_trades['LONDON']=2, max=2 → blocked."""
    state = _state(session_trades={"LONDON": 2})
    result = is_trade_limit_allowed(state, _cfg(max_trades_per_session=2), _NOW, "LONDON")
    assert result.allowed is False
    assert "session" in result.reason.lower()


def test_cooldown_blocks_within_period():
    """FR-019: last_sl 30 min ago, cooldown=2h → blocked."""
    last_sl = _NOW - timedelta(minutes=30)
    state = _state(last_sl_time=last_sl)
    result = is_trade_limit_allowed(state, _cfg(cooldown_after_sl_hours=2.0), _NOW, "LONDON")
    assert result.allowed is False
    assert "cooldown" in result.reason.lower()


def test_cooldown_allows_after_period():
    """FR-019: last_sl 3 hours ago, cooldown=2h → allowed."""
    last_sl = _NOW - timedelta(hours=3)
    state = _state(last_sl_time=last_sl)
    result = is_trade_limit_allowed(state, _cfg(cooldown_after_sl_hours=2.0), _NOW, "LONDON")
    assert result.allowed is True


def test_cooldown_allows_when_no_sl():
    """FR-019: last_sl_time=None → no cooldown → allowed."""
    state = _state(last_sl_time=None)
    result = is_trade_limit_allowed(state, _cfg(), _NOW, "LONDON")
    assert result.allowed is True


def test_record_trade_opened_increments_counters():
    """FR-020: record_trade_opened increments trades_today and session_trades."""
    state = _state(trades_today=2, session_trades={"LONDON": 1})
    new_state = record_trade_opened(state, "LONDON")
    assert new_state.trades_today == 3
    assert new_state.session_trades["LONDON"] == 2


def test_record_sl_hit_sets_time():
    """FR-021: record_sl_hit sets last_sl_time to current_time (UTC)."""
    state = _state()
    new_state = record_sl_hit(state, _NOW)
    assert new_state.last_sl_time == _NOW


def test_record_sl_hit_increments_losses():
    """FR-021: record_sl_hit increments consecutive_losses by 1."""
    state = _state(consecutive_losses=1)
    new_state = record_sl_hit(state, _NOW)
    assert new_state.consecutive_losses == 2


def test_record_trade_won_resets_losses():
    """FR-022: record_trade_won resets consecutive_losses to 0."""
    state = _state(consecutive_losses=3)
    new_state = record_trade_won(state)
    assert new_state.consecutive_losses == 0
