"""Backtest Engine data models — spec009 US2 + US3."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.engine.models import Direction


@dataclass
class PerformanceMetrics:
    """Aggregate statistics from a completed backtest run — computed by compute_metrics() (T023).

    gate_results keys: "win_rate_pass", "pf_pass", "dd_pass".
    profit_factor is float('inf') when no losing trades; 0.0 when no winning trades.
    """

    total_trades:           int
    winning_trades:         int
    losing_trades:          int
    win_rate_pct:           float
    gross_profit_usd:       float
    gross_loss_usd:         float
    profit_factor:          float
    sharpe_ratio:           float
    max_drawdown_pct:       float
    max_drawdown_usd:       float
    avg_trade_duration_bars: float
    largest_single_loss_usd: float
    gate_results:           dict[str, bool]


@dataclass
class SimulatedPosition:
    """One open position in the backtest simulation.

    Created when BacktestEngine detects an ALLOWED pipeline result.
    Updated in-place by simulate_bar() on each subsequent bar until is_closed=True.
    """

    signal_id:          str
    direction:          Direction
    entry_price:        float
    sl_price:           float
    tp1_price:          float
    tp2_price:          float
    lot_size:           float
    opened_at:          datetime
    entry_signal_type:  str
    entry_confidence:   float
    pip_value_per_lot:  float = 10.0
    is_tp1_hit:         bool  = False
    is_closed:          bool  = False


@dataclass
class TradeRecord:
    """Immutable record of one closed backtest trade.

    direction MUST use the Direction enum — no string literals (contract invariant).
    """

    signal_id:          str
    direction:          Direction
    entry_price:        float
    exit_price:         float
    exit_type:          str        # "TP1", "TP2", "SL"
    pnl_usd:            float
    lot_size:           float
    opened_at:          datetime
    closed_at:          datetime
    entry_signal_type:  str
    entry_confidence:   float


@dataclass
class BacktestResult:
    """Output of BacktestEngine.run().

    equity_curve is bar-by-bar (one entry per post-warmup H1 bar).
    output_paths maps label → absolute file path for all written artifacts.
    signal_export_path kept for backward compatibility with T021 tests.
    """

    trades:              list[TradeRecord]
    equity_curve:        list[float]
    signal_export_path:  str                    = ""
    metrics:             Optional[PerformanceMetrics] = None
    config_snapshot:     dict                   = field(default_factory=dict)
    data_period_start:   Optional[datetime]     = None
    data_period_end:     Optional[datetime]     = None
    warm_up_bars_skipped: int                   = 0
    total_bars_evaluated: int                   = 0
    output_paths:        dict[str, str]         = field(default_factory=dict)
