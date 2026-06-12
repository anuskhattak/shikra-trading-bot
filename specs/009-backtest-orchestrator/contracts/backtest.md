# Contract: BacktestEngine Public API

**Module**: `src/backtest/backtest_engine.py`  
**Purpose**: Offline historical simulation using the same pipeline core as the live orchestrator.

---

## `BacktestEngine`

```python
class BacktestEngine:
    def __init__(self, config: dict) -> None:
        """Initialise backtest engine from config.

        Reads config['backtest'] section. Raises KeyError if section missing.
        Creates internal ATRService instance (separate from live — no state sharing).
        """

    def run(self, data_dir: Optional[str] = None) -> BacktestResult:
        """Run full backtest over historical OHLCV data.

        Args:
            data_dir: Directory containing XAUUSD_{TF}.csv files.
                      Defaults to config['backtest']['data_dir'].

        Returns:
            BacktestResult with trades, equity_curve, metrics, and output_paths.

        Raises:
            FileNotFoundError: if CSV files not found in data_dir.
            ValueError: if dataset too short for ATR warm-up (< 35 H1 bars).

        Side effects:
            - Writes signal export JSONL to config['backtest']['output_dir']
            - Writes trade log CSV to config['backtest']['output_dir']
            - Writes performance report JSON to config['backtest']['output_dir']
            - Logs INFO for every trade placed and WARNING for every filter block
        """
```

---

## `data_loader.load_ohlcv_csv`

```python
def load_ohlcv_csv(
    data_dir: str,
    timeframe: Timeframe,
    symbol: str = "XAUUSD",
) -> list[OHLCVBar]:
    """Load OHLCV bars from CSV file.

    Expected filename: {data_dir}/{symbol}_{timeframe.name}.csv
    Expected columns: date (YYYY-MM-DD), time (HH:MM), open, high, low, close, volume
    Column names are case-insensitive. Extra columns are ignored.

    Returns:
        list[OHLCVBar] sorted oldest-first.

    Raises:
        FileNotFoundError: if CSV file does not exist.
        ValueError: if required columns are missing or data cannot be parsed.
    """
```

---

## `position_simulator.simulate_bar`

```python
def simulate_bar(
    position: SimulatedPosition,
    bar: OHLCVBar,
) -> tuple[SimulatedPosition, Optional[TradeRecord]]:
    """Simulate one bar's effect on an open position.

    Hit detection order (conservative — D-004):
      1. Check SL hit first (bar.low <= sl_price for LONG; bar.high >= sl_price for SHORT)
      2. Check TP1 hit (if not already hit)
      3. Check TP2 hit (only after SL check)

    When SL and TP both triggered on same bar: SL wins (closes at sl_price with loss).

    TP1 partial close:
      - Closes 50% of lot at tp1_price
      - Sets sl_price = entry_price (breakeven)
      - Sets is_tp1_hit = True
      - Returns None (position still open, no TradeRecord yet)

    Returns:
        (updated_position, trade_record_or_none)
        - trade_record_or_none: populated when position closes (SL hit or TP2 hit)
    """
```

---

## `performance.compute_metrics`

```python
def compute_metrics(
    trades: list[TradeRecord],
    equity_curve: list[float],
    initial_balance: float,
) -> PerformanceMetrics:
    """Compute all performance metrics from completed trade list and equity curve.

    Win Rate: wins / total * 100 (0.0 if no trades)
    Profit Factor: gross_profit / abs(gross_loss) (float('inf') if no losses)
    Sharpe: mean(daily_returns) / std(daily_returns) * sqrt(252)
            where daily_returns[i] = (equity_curve[day_i] - equity_curve[day_i-1]) / equity_curve[day_i-1]
            Returns 0.0 if std == 0 (no variance in returns)
    Max Drawdown: max(peak - trough) / peak * 100 over equity_curve

    Returns:
        PerformanceMetrics with gate_results dict:
        {
          "win_rate_pass": win_rate_pct >= 50.0,
          "pf_pass": profit_factor >= 1.5,
          "dd_pass": max_drawdown_pct < 30.0
        }
    """
```

---

## `signal_exporter.export_signals`

```python
def export_signals(
    contexts: list[PipelineContext],
    output_path: str,
) -> None:
    """Write signal log as JSONL file for ML training (spec007).

    One JSON object per PipelineContext (one per H1 bar evaluated).
    Fields exported per row:
      timestamp, signal_type, confidence, filter_result, filter_reason,
      direction, entry_price, sl_price, atr_h1_current, atr_h1_reference,
      volatility_ratio, volatility_regime, trade_placed

    Args:
        contexts: All PipelineContext objects from the backtest run (including warm-up bars).
        output_path: Full path to output .jsonl file (created or overwritten).

    Raises:
        IOError: if output directory does not exist or file cannot be written.
    """
```
