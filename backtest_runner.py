"""Backtest runner CLI — loads config, runs backtest, prints performance report (spec009 T026).

Usage:
    python backtest_runner.py

Exit codes:
    0 — all 3 quality gates pass  (win_rate ≥ 50%, profit_factor ≥ 1.5, max_drawdown < 30%)
    1 — one or more gates fail, or a fatal error occurred

Expects:
    config.yaml in the working directory
    OHLCV CSV files in config['backtest']['data_dir']:
        XAUUSD_H1.csv, XAUUSD_H4.csv, XAUUSD_D1.csv, XAUUSD_M5.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from src.backtest.backtest_engine import BacktestEngine

_SEP  = "=" * 46
_LINE = "-" * 46


def _gate_label(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def _fmt_pf(pf: float) -> str:
    return f"{pf:.3f}" if pf != float("inf") else "   inf"


def main() -> None:
    """Load config, run backtest, print performance report, exit 0 (all gates pass) or 1."""
    config_path = Path("config.yaml")
    if not config_path.exists():
        print("ERROR: config.yaml not found in current directory", file=sys.stderr)
        sys.exit(1)

    with config_path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)

    engine = BacktestEngine(config)
    result = engine.run()
    m = result.metrics

    if m is None:
        print("ERROR: No metrics computed — check backtest logs", file=sys.stderr)
        sys.exit(1)

    # ── Formatted report ───────────────────────────────────────────────────────
    start_str = (
        result.data_period_start.strftime("%Y-%m-%d")
        if result.data_period_start else "N/A"
    )
    end_str = (
        result.data_period_end.strftime("%Y-%m-%d")
        if result.data_period_end else "N/A"
    )

    print(_SEP)
    print("  SHIKRA BACKTEST PERFORMANCE REPORT")
    print(_SEP)
    print(f"  Period         : {start_str} -> {end_str}")
    print(f"  Bars Evaluated : {result.total_bars_evaluated}"
          f"  ({result.warm_up_bars_skipped} warm-up skipped)")
    print(f"  Total Trades   : {m.total_trades}"
          f"  ({m.winning_trades}W / {m.losing_trades}L)")
    print(_LINE)
    print(f"  Win Rate       : {m.win_rate_pct:>7.2f}%   [>=50%]  "
          f"{_gate_label(m.gate_results['win_rate_pass'])}")
    print(f"  Profit Factor  : {_fmt_pf(m.profit_factor)}   [>=1.5]  "
          f"{_gate_label(m.gate_results['pf_pass'])}")
    print(f"  Max Drawdown   : {m.max_drawdown_pct:>7.2f}%   [<30%]   "
          f"{_gate_label(m.gate_results['dd_pass'])}")
    print(f"  Sharpe Ratio   : {m.sharpe_ratio:>7.3f}")
    print(_LINE)
    print(f"  Gross Profit   : ${m.gross_profit_usd:>10.2f}")
    print(f"  Gross Loss     : ${m.gross_loss_usd:>10.2f}")
    print(f"  Avg Duration   : {m.avg_trade_duration_bars:>7.1f} bars")
    print(f"  Largest Loss   : ${m.largest_single_loss_usd:>10.2f}")
    print(_SEP)

    # ── Quality gate result ────────────────────────────────────────────────────
    all_pass = all(m.gate_results.values())
    print()
    if all_pass:
        print("=== QUALITY GATE RESULT: PASS ===")
    else:
        print("=== QUALITY GATE RESULT: FAIL ===")
        gate_names = {
            "win_rate_pass": f"Win Rate {m.win_rate_pct:.2f}% < 50%",
            "pf_pass":       f"Profit Factor {_fmt_pf(m.profit_factor).strip()} < 1.5",
            "dd_pass":       f"Max Drawdown {m.max_drawdown_pct:.2f}% ≥ 30%",
        }
        for key, passed in m.gate_results.items():
            if not passed:
                print(f"  FAILED: {gate_names[key]}")

    # ── Output file paths ──────────────────────────────────────────────────────
    if result.output_paths:
        print()
        print("Output files:")
        for label, path in result.output_paths.items():
            print(f"  {label:8s}: {path}")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
