"""Unit tests for src/risk/drawdown_guard.py — spec003 FR-012 to FR-015a.

TDD: all tests written BEFORE implementation; they must FAIL until T008 is complete.
Run: pytest tests/unit/test_risk_drawdown_guard.py
"""
import pytest

from src.risk.drawdown_guard import check_drawdown, get_drawdown_pct, reset_daily_state
from src.risk.models import RiskState


def _state(day_start_equity: float = 10_000.0, trades_today: int = 0) -> RiskState:
    return RiskState(day_start_equity=day_start_equity, trades_today=trades_today)


# ---------------------------------------------------------------------------
# T007 — US3: Daily drawdown guard (FR-012 to FR-015)
# ---------------------------------------------------------------------------


def test_drawdown_blocks_at_limit():
    """SC-002: equity=9400, start=10000, limit=5% → drawdown=6% → blocked."""
    result = check_drawdown(day_start_equity=10_000.0, current_equity=9_400.0, max_pct=5.0)
    assert result.allowed is False
    assert "6.0" in result.reason
    assert "5.0" in result.reason


def test_drawdown_allows_below_limit():
    """FR-014: equity=9600, start=10000, limit=5% → drawdown=4% → allowed."""
    result = check_drawdown(day_start_equity=10_000.0, current_equity=9_600.0, max_pct=5.0)
    assert result.allowed is True


def test_drawdown_reason_string_correct():
    """FR-014: reason string must include both actual% and limit% when blocked."""
    result = check_drawdown(day_start_equity=10_000.0, current_equity=9_400.0, max_pct=5.0)
    assert "6.0" in result.reason
    assert "5.0" in result.reason


def test_drawdown_at_exact_limit_blocks():
    """FR-014 boundary: equity=9500 → drawdown=exactly 5.0% → blocked (≥ not >)."""
    result = check_drawdown(day_start_equity=10_000.0, current_equity=9_500.0, max_pct=5.0)
    assert result.allowed is False


def test_reset_updates_day_start_equity():
    """FR-015: reset_daily_state() sets day_start_equity to current_equity."""
    state = _state(day_start_equity=10_000.0)
    new_state = reset_daily_state(state, current_equity=9_800.0)
    assert new_state.day_start_equity == 9_800.0


def test_reset_clears_trades_today():
    """FR-015: reset_daily_state() resets trades_today to 0."""
    state = _state(trades_today=4)
    new_state = reset_daily_state(state, current_equity=10_000.0)
    assert new_state.trades_today == 0


def test_startup_mid_day_initialization():
    """FR-015a: RiskState(day_start_equity=current_equity) reflects startup equity.

    Known limitation: mid-day restart clears that day's drawdown history.
    This test documents the expected behaviour, not a bug.
    """
    current_equity = 9_750.0
    state = RiskState(day_start_equity=current_equity)
    assert state.day_start_equity == current_equity
    # Immediately after startup no drawdown has occurred
    result = check_drawdown(
        day_start_equity=state.day_start_equity,
        current_equity=current_equity,
        max_pct=5.0,
    )
    assert result.allowed is True
