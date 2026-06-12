"""Backtest performance metrics computation — spec009 T023."""
from __future__ import annotations

import math
import statistics
from datetime import date

from src.backtest.models import PerformanceMetrics, TradeRecord

_WIN_RATE_GATE  = 50.0   # %
_PF_GATE        = 1.5
_MAX_DD_GATE    = 30.0   # %


def compute_metrics(
    trades: list[TradeRecord],
    equity_curve: list[float],
    initial_balance: float,
    bar_dates: list[date],
) -> PerformanceMetrics:
    """Compute aggregate performance metrics from a completed backtest.

    equity_curve and bar_dates must be parallel lists — one entry per post-warmup H1 bar.
    Sharpe is annualized using daily returns (last H1 equity per calendar day) × sqrt(252).
    profit_factor = inf when no losing trades; 0.0 when no winning trades.
    gate_results keys: "win_rate_pass", "pf_pass", "dd_pass".
    """
    total = len(trades)

    winning = [t for t in trades if t.pnl_usd > 0]
    losing  = [t for t in trades if t.pnl_usd < 0]

    gross_profit = sum(t.pnl_usd for t in winning)
    gross_loss   = abs(sum(t.pnl_usd for t in losing))

    win_rate_pct = len(winning) / total * 100.0 if total > 0 else 0.0

    if gross_loss == 0.0:
        profit_factor = float("inf")
    elif gross_profit == 0.0:
        profit_factor = 0.0
    else:
        profit_factor = gross_profit / gross_loss

    sharpe      = _compute_sharpe(equity_curve, bar_dates)
    dd_pct, dd_usd = _compute_max_drawdown(equity_curve, initial_balance)

    avg_duration = 0.0
    if trades:
        # H1 data: 1 bar ≈ 1 hour — duration in hours approximates duration in bars
        durations = [
            (t.closed_at - t.opened_at).total_seconds() / 3600.0
            for t in trades
        ]
        avg_duration = sum(durations) / len(durations)

    largest_loss = abs(min((t.pnl_usd for t in losing), default=0.0))

    gate_results = {
        "win_rate_pass": win_rate_pct >= _WIN_RATE_GATE,
        "pf_pass":       profit_factor >= _PF_GATE,
        "dd_pass":       dd_pct < _MAX_DD_GATE,
    }

    return PerformanceMetrics(
        total_trades=total,
        winning_trades=len(winning),
        losing_trades=len(losing),
        win_rate_pct=win_rate_pct,
        gross_profit_usd=gross_profit,
        gross_loss_usd=gross_loss,
        profit_factor=profit_factor,
        sharpe_ratio=sharpe,
        max_drawdown_pct=dd_pct,
        max_drawdown_usd=dd_usd,
        avg_trade_duration_bars=avg_duration,
        largest_single_loss_usd=largest_loss,
        gate_results=gate_results,
    )


def _compute_sharpe(equity_curve: list[float], bar_dates: list[date]) -> float:
    """Annualized Sharpe from bar-level equity grouped by calendar day.

    Uses last H1 bar equity per day as the day's closing equity.
    Returns 0.0 if fewer than 2 trading days or if daily return std == 0.
    """
    if len(equity_curve) != len(bar_dates) or len(equity_curve) < 2:
        return 0.0

    # last bar equity per calendar day (later assignments overwrite earlier ones)
    daily_equity: dict[date, float] = {}
    for d, e in zip(bar_dates, equity_curve):
        daily_equity[d] = e

    sorted_days = sorted(daily_equity)
    if len(sorted_days) < 2:
        return 0.0

    day_equities = [daily_equity[d] for d in sorted_days]
    daily_returns = [
        (day_equities[i] - day_equities[i - 1]) / day_equities[i - 1]
        for i in range(1, len(day_equities))
    ]

    if len(daily_returns) < 2:
        return 0.0

    try:
        std_ret = statistics.stdev(daily_returns)
    except statistics.StatisticsError:
        return 0.0

    if std_ret == 0.0:
        return 0.0

    mean_ret = statistics.mean(daily_returns)
    return mean_ret / std_ret * math.sqrt(252)


def _compute_max_drawdown(
    equity_curve: list[float],
    initial_balance: float,
) -> tuple[float, float]:
    """Max drawdown % and USD by tracking running peak through the full equity curve.

    Peak is initialized to initial_balance (pre-trade starting point).
    """
    if not equity_curve:
        return 0.0, 0.0

    peak       = initial_balance
    max_dd_pct = 0.0
    max_dd_usd = 0.0

    for equity in equity_curve:
        if equity > peak:
            peak = equity
        dd_usd = peak - equity
        dd_pct = dd_usd / peak * 100.0 if peak > 0 else 0.0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd_usd = dd_usd

    return max_dd_pct, max_dd_usd
