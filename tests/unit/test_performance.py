"""Unit tests for src/backtest/performance.py — spec009 T024.

6 tests:
  1. Hand-calculated 10-trade scenario — win_rate and profit_factor within ±0.1%
  2. Zero trades — metrics are 0/0/inf as appropriate
  3. No losing trades — profit_factor = float('inf')
  4. std of daily returns == 0 — sharpe_ratio = 0.0
  5. PASS gates: win_rate=55%, PF=1.6, MaxDD=20% — all three gate_results True
  6. FAIL gate: MaxDD=35% — dd_pass=False
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from src.backtest.models import TradeRecord
from src.backtest.performance import compute_metrics
from src.engine.models import Direction

_BASE_DATE = date(2024, 1, 1)
_BASE_DT   = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)


def _make_trade(
    pnl: float,
    day_offset: int = 0,
    duration_hours: float = 2.0,
) -> TradeRecord:
    opened = _BASE_DT + timedelta(days=day_offset)
    closed = opened + timedelta(hours=duration_hours)
    direction = Direction.LONG if pnl >= 0 else Direction.SHORT
    return TradeRecord(
        signal_id=f"sig-{day_offset}",
        direction=direction,
        entry_price=2000.0,
        exit_price=2000.0 + pnl / 0.10 / 10.0,   # back-calculated (not used in metrics)
        exit_type="TP2" if pnl > 0 else "SL",
        pnl_usd=pnl,
        lot_size=0.10,
        opened_at=opened,
        closed_at=closed,
        entry_signal_type="BOS_BULLISH",
        entry_confidence=0.75,
    )


def _equity_curve_from_trades(
    trades: list[TradeRecord],
    initial: float = 10_000.0,
) -> tuple[list[float], list[date]]:
    """Build bar-by-bar (one bar per trade for simplicity) equity and dates."""
    equity = initial
    eq_list: list[float]  = []
    dt_list: list[date]  = []
    for t in trades:
        equity += t.pnl_usd
        eq_list.append(equity)
        dt_list.append(t.closed_at.date())
    return eq_list, dt_list


# ── Test 1: Hand-calculated 10-trade scenario ────────────────────────────────

class TestHandCalculated10Trades:
    def test_win_rate_and_profit_factor_within_tolerance(self):
        """6 wins @ +$100, 4 losses @ -$80 → WR=60%, PF=1.875 (verified ±0.1%)."""
        trades = (
            [_make_trade(pnl=100.0, day_offset=i)    for i in range(6)]
            + [_make_trade(pnl=-80.0, day_offset=i)  for i in range(6, 10)]
        )
        equity_curve, bar_dates = _equity_curve_from_trades(trades)

        m = compute_metrics(trades, equity_curve, 10_000.0, bar_dates)

        assert m.total_trades    == 10
        assert m.winning_trades  == 6
        assert m.losing_trades   == 4
        assert m.win_rate_pct    == pytest.approx(60.0,   rel=0.001)
        assert m.gross_profit_usd == pytest.approx(600.0, rel=0.001)
        assert m.gross_loss_usd   == pytest.approx(320.0, rel=0.001)
        assert m.profit_factor    == pytest.approx(1.875, rel=0.001)
        # Max drawdown: peak=10600 after 6 wins, trough=10280 after 4 losses
        # dd% = (10600 - 10280) / 10600 ≈ 3.019%
        assert m.max_drawdown_pct == pytest.approx(3.019, rel=0.01)
        assert m.max_drawdown_usd == pytest.approx(320.0, rel=0.001)
        assert m.largest_single_loss_usd == pytest.approx(80.0, rel=0.001)


# ── Test 2: Zero trades ──────────────────────────────────────────────────────

class TestZeroTrades:
    def test_zero_trades_returns_safe_defaults(self):
        """No trades → win_rate=0.0, profit_factor=inf (no losers), drawdown=0.0."""
        m = compute_metrics([], [], 10_000.0, [])

        assert m.total_trades   == 0
        assert m.winning_trades == 0
        assert m.losing_trades  == 0
        assert m.win_rate_pct   == 0.0
        assert m.profit_factor  == float("inf")
        assert m.sharpe_ratio   == 0.0
        assert m.max_drawdown_pct == 0.0
        assert m.max_drawdown_usd == 0.0
        assert m.avg_trade_duration_bars == 0.0
        assert m.largest_single_loss_usd == 0.0


# ── Test 3: No losing trades → profit_factor = inf ───────────────────────────

class TestNoLosingTrades:
    def test_profit_factor_is_inf_when_all_trades_are_wins(self):
        """All wins, zero losses → profit_factor must be float('inf')."""
        trades = [_make_trade(pnl=100.0, day_offset=i) for i in range(5)]
        equity_curve, bar_dates = _equity_curve_from_trades(trades)

        m = compute_metrics(trades, equity_curve, 10_000.0, bar_dates)

        assert m.profit_factor == float("inf")
        assert m.losing_trades == 0
        assert m.gross_loss_usd == 0.0


# ── Test 4: std of returns == 0 → sharpe = 0.0 ───────────────────────────────

class TestZeroReturnStd:
    def test_sharpe_is_zero_when_equity_is_flat(self):
        """Flat equity (no trades) → all daily returns == 0 → std == 0 → sharpe = 0.0."""
        # Equity never changes → same value every bar → daily returns all 0.0 → std=0
        n = 20
        equity_curve = [10_000.0] * n
        bar_dates = [_BASE_DATE + timedelta(days=i) for i in range(n)]

        m = compute_metrics([], equity_curve, 10_000.0, bar_dates)

        assert m.sharpe_ratio == 0.0


# ── Test 5: All gates PASS ───────────────────────────────────────────────────

class TestAllGatesPass:
    def test_gate_results_all_true_when_thresholds_met(self):
        """win_rate=55%, PF≈1.6, MaxDD<20% → all three gate_results True."""
        # 11 wins @ +$100, 9 losses @ -$62.5 → WR=55%, PF≈1.778
        trades = (
            [_make_trade(pnl=100.0, day_offset=i)       for i in range(11)]
            + [_make_trade(pnl=-62.5, day_offset=i + 11) for i in range(9)]
        )
        equity_curve, bar_dates = _equity_curve_from_trades(trades)

        m = compute_metrics(trades, equity_curve, 10_000.0, bar_dates)

        assert m.win_rate_pct >= 50.0
        assert m.profit_factor >= 1.5
        assert m.max_drawdown_pct < 30.0
        assert m.gate_results["win_rate_pass"] is True
        assert m.gate_results["pf_pass"]       is True
        assert m.gate_results["dd_pass"]        is True


# ── Test 6: dd_pass FAIL ─────────────────────────────────────────────────────

class TestDrawdownGateFail:
    def test_dd_pass_false_when_drawdown_exceeds_30pct(self):
        """MaxDD > 30% → dd_pass must be False; other gates unaffected."""
        # Equity drops from 10000 to 6500 → dd = 35%
        initial = 10_000.0
        n = 10
        # Equity: starts at 10000, drops 350 per bar for 10 bars → final = 6500
        equity_curve = [initial - 350.0 * (i + 1) for i in range(n)]
        bar_dates     = [_BASE_DATE + timedelta(days=i) for i in range(n)]

        # Fabricate trades that explain the equity drop (not used in dd calculation)
        trades = [_make_trade(pnl=-350.0, day_offset=i) for i in range(n)]

        m = compute_metrics(trades, equity_curve, initial, bar_dates)

        assert m.max_drawdown_pct > 30.0
        assert m.gate_results["dd_pass"] is False
