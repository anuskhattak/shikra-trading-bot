"""Backtest Engine — runs the shared pipeline over historical CSV data (spec009 US2 + US3).

No MetaTrader5 import anywhere in this file (FR-009, FR-017).
Uses the same run_pipeline() function as StrategyOrchestrator — no logic duplication.
"""
from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from src.analysis.atr_service import ATRService
from src.analysis.h4_bias import H4BiasService
from src.analysis.models import OHLCVBar, Timeframe
from src.backtest.data_loader import load_ohlcv_csv
from src.backtest.models import BacktestResult, SimulatedPosition, TradeRecord
from src.backtest.performance import compute_metrics
from src.backtest.position_simulator import simulate_bar
from src.backtest.signal_exporter import export_signals
from src.filters.models import FilterResult
from src.orchestrator.models import PipelineContext
from src.orchestrator.pipeline import run_pipeline

_WARMUP_BARS = 35   # H1 bars consumed for ATR warm-up before trading starts (FR-009)
_WINDOW      = 150  # bars per timeframe passed to run_pipeline


class BacktestEngine:
    """Runs the 4-stage pipeline over historical OHLCV CSV data.

    News filter is disabled (news_events=[]) and spread is fixed (FR-011).
    First 35 H1 bars are consumed as ATR warm-up; no trades are opened during that period.
    """

    def __init__(self, config: dict) -> None:
        """Initialise the engine with the full application config dict."""
        self._config = config
        self._atr_service = ATRService(config)
        self._h4_bias_service = H4BiasService(config)

    def run(self) -> BacktestResult:
        """Run full backtest and return a BacktestResult with performance metrics.

        Loads CSVs for all 4 timeframes, iterates H1 bars as the primary clock,
        runs run_pipeline() for each post-warmup bar, simulates open positions,
        calls compute_metrics(), and writes report JSON + trades CSV + signals JSONL.
        """
        cfg_bt      = self._config["backtest"]
        data_dir    = cfg_bt["data_dir"]
        spread_usd  = float(cfg_bt["spread_usd"])
        initial_bal = float(cfg_bt["initial_balance"])
        output_dir  = Path(cfg_bt["output_dir"])
        pip_val     = float(self._config.get("risk", {}).get("pip_value_per_lot", 10.0))

        bars_by_tf = _load_all_timeframes(data_dir)
        h1_bars    = bars_by_tf.get(Timeframe.H1, [])

        if not h1_bars:
            logger.warning("No H1 bars loaded — returning empty BacktestResult")
            return BacktestResult(trades=[], equity_curve=[initial_bal])

        contexts:       list[PipelineContext]   = []
        open_positions: list[SimulatedPosition] = []
        trade_records:  list[TradeRecord]       = []
        bar_equity:     list[float]             = []   # one entry per post-warmup bar
        bar_dates:      list                    = []   # parallel date list for Sharpe
        balance = initial_bal

        data_period_start = None
        data_period_end   = None

        for i, h1_bar in enumerate(h1_bars):
            bars_dict = _build_bars_dict(bars_by_tf, h1_bar.timestamp, _WINDOW)

            # Warm-up: refresh ATR service but skip pipeline and trading
            if i < _WARMUP_BARS:
                for tf, bars in bars_dict.items():
                    try:
                        self._atr_service.refresh(tf, bars)
                    except Exception:
                        pass
                continue

            if data_period_start is None:
                data_period_start = h1_bar.timestamp
            data_period_end = h1_bar.timestamp

            signal_id = str(uuid.uuid4())
            ctx = PipelineContext(
                signal_id=signal_id,
                timeframe=Timeframe.H1,
                bars=bars_dict,
                now_utc=h1_bar.timestamp,
                spread_usd=spread_usd,
                news_events=[],           # FR-011: news filter disabled in backtest
                mode="backtest",
                balance=balance,
                current_equity=balance,
            )
            ctx = run_pipeline(ctx, self._atr_service, self._config, self._h4_bias_service)
            contexts.append(ctx)

            # Simulate existing open positions before opening new ones
            still_open: list[SimulatedPosition] = []
            for pos in open_positions:
                updated, record = simulate_bar(pos, h1_bar)
                if record is not None:
                    trade_records.append(record)
                    balance += record.pnl_usd
                if not updated.is_closed:
                    still_open.append(updated)
            open_positions = still_open

            # Open a new position when the pipeline returns ALLOWED with valid risk calc
            if (
                ctx.filter_result is not None
                and ctx.filter_result.final_result == FilterResult.ALLOWED
                and ctx.risk_calc is not None
                and ctx.entry_signal is not None
            ):
                entry_price = (
                    ctx.entry_signal.entry_zone_top + ctx.entry_signal.entry_zone_bottom
                ) / 2.0
                open_positions.append(SimulatedPosition(
                    signal_id=signal_id,
                    direction=ctx.entry_signal.direction,
                    entry_price=entry_price,
                    sl_price=ctx.risk_calc.sl_price,
                    tp1_price=ctx.risk_calc.tp1_price,
                    tp2_price=ctx.risk_calc.tp2_price,
                    lot_size=ctx.risk_calc.lot_size,
                    opened_at=h1_bar.timestamp,
                    entry_signal_type=ctx.entry_signal.signal_type.value,
                    entry_confidence=ctx.entry_signal.confidence,
                    pip_value_per_lot=pip_val,
                ))

            # Bar-by-bar equity snapshot (after simulation, before next bar)
            bar_equity.append(balance)
            bar_dates.append(h1_bar.timestamp.date())

        # ── Artifacts ──────────────────────────────────────────────────────────
        output_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        signals_path = output_dir / f"signals_{date_str}.jsonl"
        export_signals(contexts, signals_path, self._config)

        metrics = compute_metrics(trade_records, bar_equity, initial_bal, bar_dates)

        report_path = output_dir / f"report_{date_str}.json"
        _write_report_json(
            report_path, metrics, self._config,
            data_period_start, data_period_end,
            _WARMUP_BARS, len(bar_equity),
        )

        trades_path = output_dir / f"trades_{date_str}.csv"
        _write_trades_csv(trades_path, trade_records)

        output_paths = {
            "signals": str(signals_path),
            "report":  str(report_path),
            "trades":  str(trades_path),
        }

        return BacktestResult(
            trades=trade_records,
            equity_curve=bar_equity,
            signal_export_path=str(signals_path),
            metrics=metrics,
            config_snapshot=cfg_bt,
            data_period_start=data_period_start,
            data_period_end=data_period_end,
            warm_up_bars_skipped=_WARMUP_BARS,
            total_bars_evaluated=len(bar_equity),
            output_paths=output_paths,
        )


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_all_timeframes(data_dir: str) -> dict[Timeframe, list[OHLCVBar]]:
    result: dict[Timeframe, list[OHLCVBar]] = {}
    for tf in Timeframe:
        try:
            bars = load_ohlcv_csv(data_dir, tf)
            result[tf] = bars
            logger.info(f"Loaded {len(bars)} {tf.name} bars from {data_dir}")
        except FileNotFoundError:
            result[tf] = []
            logger.warning(f"No CSV for {tf.name} in {data_dir} — timeframe skipped")
    return result


def _build_bars_dict(
    bars_by_tf: dict[Timeframe, list[OHLCVBar]],
    cutoff: datetime,
    window: int,
) -> dict[Timeframe, list[OHLCVBar]]:
    """Return the last `window` bars per TF where timestamp <= cutoff."""
    result: dict[Timeframe, list[OHLCVBar]] = {}
    for tf, bars in bars_by_tf.items():
        sliced = _aligned_window(bars, cutoff, window)
        if sliced:
            result[tf] = sliced
    return result


def _aligned_window(bars: list[OHLCVBar], cutoff: datetime, window: int) -> list[OHLCVBar]:
    """Binary-search-style slice: all bars with timestamp <= cutoff, capped at `window`."""
    end = 0
    for j, b in enumerate(bars):
        if b.timestamp <= cutoff:
            end = j + 1
        else:
            break
    return bars[max(0, end - window):end]


def _write_report_json(
    path: Path,
    metrics,
    config: dict,
    period_start,
    period_end,
    warmup_bars: int,
    total_bars: int,
) -> None:
    pf = metrics.profit_factor
    report = {
        "generated_at":        datetime.now(timezone.utc).isoformat(),
        "data_period_start":   period_start.isoformat() if period_start else None,
        "data_period_end":     period_end.isoformat()   if period_end   else None,
        "warm_up_bars_skipped": warmup_bars,
        "total_bars_evaluated": total_bars,
        "config_snapshot":     config.get("backtest", {}),
        "metrics": {
            "total_trades":            metrics.total_trades,
            "winning_trades":          metrics.winning_trades,
            "losing_trades":           metrics.losing_trades,
            "win_rate_pct":            round(metrics.win_rate_pct, 4),
            "gross_profit_usd":        round(metrics.gross_profit_usd, 4),
            "gross_loss_usd":          round(metrics.gross_loss_usd, 4),
            "profit_factor":           round(pf, 4) if pf != float("inf") else "inf",
            "sharpe_ratio":            round(metrics.sharpe_ratio, 4),
            "max_drawdown_pct":        round(metrics.max_drawdown_pct, 4),
            "max_drawdown_usd":        round(metrics.max_drawdown_usd, 4),
            "avg_trade_duration_bars": round(metrics.avg_trade_duration_bars, 2),
            "largest_single_loss_usd": round(metrics.largest_single_loss_usd, 4),
            "gate_results":            metrics.gate_results,
        },
    }
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info(f"Report written: {path}")


def _write_trades_csv(path: Path, trades: list[TradeRecord]) -> None:
    fields = [
        "signal_id", "direction", "entry_price", "exit_price", "exit_type",
        "pnl_usd", "lot_size", "opened_at", "closed_at",
        "entry_signal_type", "entry_confidence",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for t in trades:
            writer.writerow({
                "signal_id":         t.signal_id,
                "direction":         t.direction.value,
                "entry_price":       t.entry_price,
                "exit_price":        t.exit_price,
                "exit_type":         t.exit_type,
                "pnl_usd":           round(t.pnl_usd, 4),
                "lot_size":          t.lot_size,
                "opened_at":         t.opened_at.isoformat(),
                "closed_at":         t.closed_at.isoformat(),
                "entry_signal_type": t.entry_signal_type,
                "entry_confidence":  t.entry_confidence,
            })
    logger.info(f"Trades CSV written: {path}")
