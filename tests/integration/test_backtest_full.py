"""Integration tests for BacktestEngine — spec009 T021.

3 tests:
  1. Full run completes without exceptions on synthetic OHLCV data
  2. JSONL signal file is written with at least one valid row per evaluated bar
  3. Determinism — two independent runs with the same data produce identical P&L lists
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.analysis.models import Timeframe
from src.backtest.backtest_engine import BacktestEngine

# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------

_START = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)  # Monday, London session


def _weekday_hours(start: datetime, count: int) -> list[datetime]:
    """Generate `count` hourly timestamps that fall on Mon–Fri (skip weekends)."""
    result = []
    ts = start
    while len(result) < count:
        if ts.weekday() < 5:   # 0=Mon … 4=Fri
            result.append(ts)
        ts += timedelta(hours=1)
    return result


def _h1_csv(timestamps: list[datetime]) -> str:
    """Minimal H1 OHLCV CSV; price oscillates around 2000 to trigger structure breaks."""
    lines = ["date,time,open,high,low,close,tick_volume"]
    price = 2000.0
    for i, ts in enumerate(timestamps):
        # Create alternating up/down moves to allow SMC engine to detect structure
        move = 3.0 * (1 if i % 8 < 4 else -1)
        price_open = price
        price_close = price + move
        high = max(price_open, price_close) + 5.0 + (i % 5)
        low  = min(price_open, price_close) - 5.0 - (i % 3)
        lines.append(
            f"{ts.strftime('%Y.%m.%d')},{ts.strftime('%H:%M')},"
            f"{price_open:.2f},{high:.2f},{low:.2f},{price_close:.2f},1000"
        )
        price = price_close
    return "\n".join(lines) + "\n"


def _h4_csv(h1_timestamps: list[datetime]) -> str:
    """One H4 bar per 4 H1 bars, aligned to 4-hour boundaries."""
    lines = ["date,time,open,high,low,close,tick_volume"]
    h4_seen: set[datetime] = set()
    price = 2000.0
    for ts in h1_timestamps:
        h4_ts = ts.replace(minute=0, second=0, microsecond=0)
        h4_ts = h4_ts.replace(hour=(h4_ts.hour // 4) * 4)
        if h4_ts not in h4_seen:
            h4_seen.add(h4_ts)
            h = high = price + 8.0
            l = low  = price - 8.0
            lines.append(
                f"{h4_ts.strftime('%Y.%m.%d')},{h4_ts.strftime('%H:%M')},"
                f"{price:.2f},{h:.2f},{l:.2f},{price + 2:.2f},5000"
            )
    return "\n".join(lines) + "\n"


def _d1_csv(h1_timestamps: list[datetime]) -> str:
    """One D1 bar per calendar day."""
    lines = ["date,time,open,high,low,close,tick_volume"]
    days_seen: set[datetime] = set()
    price = 2000.0
    for ts in h1_timestamps:
        d1_ts = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        if d1_ts not in days_seen:
            days_seen.add(d1_ts)
            lines.append(
                f"{d1_ts.strftime('%Y.%m.%d')},{d1_ts.strftime('%H:%M')},"
                f"{price:.2f},{price + 15:.2f},{price - 15:.2f},{price + 5:.2f},20000"
            )
    return "\n".join(lines) + "\n"


def _m5_csv(h1_timestamps: list[datetime]) -> str:
    """12 M5 bars per H1 bar (covering the hour up to each H1 close)."""
    lines = ["date,time,open,high,low,close,tick_volume"]
    price = 2000.0
    for ts in h1_timestamps:
        for m in range(0, 60, 5):
            m5_ts = ts.replace(minute=m)
            lines.append(
                f"{m5_ts.strftime('%Y.%m.%d')},{m5_ts.strftime('%H:%M')},"
                f"{price:.2f},{price + 2:.2f},{price - 2:.2f},{price + 0.5:.2f},200"
            )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def bt_config_and_data(tmp_path):
    """Write synthetic CSVs and return a complete BacktestEngine config."""
    data_dir   = tmp_path / "data"
    output_dir = tmp_path / "results"
    log_dir    = tmp_path / "logs"
    data_dir.mkdir()
    output_dir.mkdir()
    log_dir.mkdir()

    # 100 H1 weekday bars — enough for 35-bar warmup + many tradeable bars
    timestamps = _weekday_hours(_START, 100)
    (data_dir / "XAUUSD_H1.csv").write_text(_h1_csv(timestamps))
    (data_dir / "XAUUSD_H4.csv").write_text(_h4_csv(timestamps))
    (data_dir / "XAUUSD_D1.csv").write_text(_d1_csv(timestamps))
    (data_dir / "XAUUSD_M5.csv").write_text(_m5_csv(timestamps))

    config = {
        "backtest": {
            "initial_balance": 10000.0,
            "spread_usd": 0.35,
            "data_dir": str(data_dir),
            "output_dir": str(output_dir),
            "risk_percent": 1.0,
        },
        "analysis": {
            "atr": {
                "period": 14,
                "reference_period": 20,
                "adaptive_multipliers": {
                    "sl": {"LOW": 1.0, "NORMAL": 1.5, "EXTREME": 2.0},
                    "tp": {"LOW": 2.0, "NORMAL": 3.0, "EXTREME": 4.0},
                },
            }
        },
        "risk": {
            "sl_atr_multiplier":  1.5,
            "tp1_rr_ratio":       1.5,
            "tp2_rr_ratio":       3.0,
            "risk_percent":       1.0,
            "pip_value_per_lot":  10.0,
            "max_lot_size":       5.0,
            "min_lot_size":       0.01,
        },
        "filters": {
            "spread":     {"max_spread_usd": 0.50},
            "news":       {
                "pre_event_minutes": 30, "post_event_minutes": 15,
                "impact_levels": ["HIGH"], "calendar_path": "",
            },
            "volatility": {
                "atr_lookback": 14, "low_atr_ratio": 0.50, "extreme_atr_ratio": 5.0
            },
        },
        "sessions": {
            "london": {
                "local_open": "08:00", "local_close": "17:00",
                "timezone": "Europe/London", "enabled": True,
            },
            "new_york": {
                "local_open": "08:00", "local_close": "17:00",
                "timezone": "America/New_York", "enabled": True,
            },
        },
        "smc_engine": {
            "fractal_n": 2,
            "lookback_window": 20,
            "equal_level_tolerance_pips": 5,
            "confidence_threshold": 0.65,
            "weights": {
                "bos_or_choch": 0.40, "fvg": 0.30,
                "order_block": 0.20, "liquidity_sweep": 0.10,
            },
            "min_candles": 50,
        },
        "logging": {
            "filters_log": str(log_dir / "filter_decisions.json"),
            "trades_log":  str(log_dir / "trades.json"),
            "signals_log": str(log_dir / "signals.json"),
        },
    }
    return config, output_dir


# ---------------------------------------------------------------------------
# Test 1: full run completes without exceptions
# ---------------------------------------------------------------------------

class TestFullRunCompletes:
    def test_run_returns_backtest_result_with_no_exception(self, bt_config_and_data):
        """BacktestEngine.run() must complete on synthetic data without raising."""
        config, _ = bt_config_and_data
        engine = BacktestEngine(config)
        result = engine.run()

        assert result is not None
        assert isinstance(result.trades, list)
        assert isinstance(result.equity_curve, list)
        assert len(result.equity_curve) >= 1
        # First equity value equals initial_balance
        assert result.equity_curve[0] == pytest.approx(10000.0)


# ---------------------------------------------------------------------------
# Test 2: JSONL signal file written with valid content
# ---------------------------------------------------------------------------

class TestJSONLWritten:
    def test_signals_file_exists_and_has_valid_rows(self, bt_config_and_data):
        """After run(), a signals_*.jsonl file must exist with parseable 13-field rows."""
        config, output_dir = bt_config_and_data
        engine = BacktestEngine(config)
        result = engine.run()

        # File path recorded in result
        signals_path = Path(result.signal_export_path)
        assert signals_path.exists(), "JSONL signals file was not created"

        lines = signals_path.read_text().strip().splitlines()
        assert len(lines) > 0, "signals JSONL is empty"

        required = {
            "timestamp", "signal_type", "confidence", "filter_result",
            "filter_reason", "direction", "entry_price", "sl_price",
            "atr_h1_current", "atr_h1_reference", "volatility_ratio",
            "volatility_regime", "trade_placed",
        }
        for line in lines:
            row = json.loads(line)
            assert required.issubset(row.keys()), (
                f"Row missing fields: {required - row.keys()}"
            )


# ---------------------------------------------------------------------------
# Test 3: deterministic — two runs produce identical P&L lists
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_two_runs_with_same_data_produce_identical_pnl_list(self, bt_config_and_data):
        """FR-015 / SC-006: running the backtest twice on the same data must give the
        same ordered list of P&L values."""
        config, _ = bt_config_and_data

        result1 = BacktestEngine(config).run()
        result2 = BacktestEngine(config).run()

        pnl1 = [t.pnl_usd for t in result1.trades]
        pnl2 = [t.pnl_usd for t in result2.trades]

        assert len(pnl1) == len(pnl2), (
            f"Trade count differs between runs: {len(pnl1)} vs {len(pnl2)}"
        )
        for i, (a, b) in enumerate(zip(pnl1, pnl2)):
            assert a == pytest.approx(b), f"P&L mismatch at trade {i}: {a} vs {b}"
