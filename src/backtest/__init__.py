"""Public API for the backtest package."""
from src.backtest.backtest_engine import BacktestEngine
from src.backtest.data_loader import load_ohlcv_csv
from src.backtest.models import (
    BacktestResult,
    PerformanceMetrics,
    SimulatedPosition,
    TradeRecord,
)
from src.backtest.performance import compute_metrics
from src.backtest.signal_exporter import export_signals

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "PerformanceMetrics",
    "SimulatedPosition",
    "TradeRecord",
    "load_ohlcv_csv",
    "compute_metrics",
    "export_signals",
]
