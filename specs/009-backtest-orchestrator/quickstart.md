# Quickstart: Backtest Suite & Strategy Orchestrator

**Feature**: `009-backtest-orchestrator` | **Branch**: `009-backtest-orchestrator`

---

## Live Trading (Strategy Orchestrator)

### Prerequisites
- MetaTrader 5 terminal installed and running (Windows only)
- Demo account credentials
- `config.yaml` configured (see Config Reference below)

### Run
```bash
python main.py
# or with custom config:
python main.py --config config.yaml
```

### Startup sequence
1. Connects to MT5 using `config.broker` credentials
2. Loads 150 bars of OHLCV history for all 4 timeframes
3. Warms up ATRService (35+ bars needed before first trade)
4. Begins polling for H1 bar closes every 10 seconds
5. Logs `[ORCHESTRATOR] Ready — watching for H1 bar closes` when warm-up complete

### Stopping
- Press `Ctrl+C` — orchestrator shuts down cleanly, disconnects from MT5
- Activate kill switch: create `logs/kill_switch.json` with `{"active": true}`
  - New orders stop immediately; open position management continues

### Live logs
```
logs/filter_decisions.json   — filter decisions per signal (ALLOWED/BLOCKED + reason)
logs/trades.json             — audit log for all orders placed and rejected
logs/false_signals.json      — SMC signals below confidence threshold (discarded)
```

---

## Backtesting

### Prerequisites
- Historical OHLCV CSV files in `data/historical/`:
  ```
  data/historical/XAUUSD_H1.csv
  data/historical/XAUUSD_D1.csv
  data/historical/XAUUSD_H4.csv
  data/historical/XAUUSD_M5.csv
  ```
- CSV format: `date,time,open,high,low,close,volume` (MT5 history export format)

### Exporting historical data from MT5
1. Open MetaTrader 5 → Tools → History Center
2. Select XAUUSD → H1 → Export as CSV
3. Save to `data/historical/XAUUSD_H1.csv`
4. Repeat for D1, H4, M5

### Run backtest
```bash
python backtest_runner.py
# or with custom data dir:
python backtest_runner.py --data data/historical --config config.yaml
```

### Backtest output
```
backtest/results/signals_YYYYMMDD.jsonl    — signal export for ML training (spec007)
backtest/results/trades_YYYYMMDD.csv       — all trades with entry/exit details
backtest/results/report_YYYYMMDD.json      — performance metrics + PASS/FAIL gates
```

### Sample performance report output
```
=== BACKTEST PERFORMANCE REPORT ===
Period: 2022-01-01 → 2024-01-01 (2 years, 17,520 H1 bars)
Warm-up bars skipped: 35

Total trades:      148
Winning trades:    79  (53.4%)  ✅ PASS (≥ 50%)
Profit Factor:     1.73         ✅ PASS (≥ 1.5)
Max Drawdown:      18.2%        ✅ PASS (< 30%)
Sharpe Ratio:      0.94

Gross Profit:      $4,230.50
Gross Loss:       -$2,445.20
Net P&L:           $1,785.30
Largest Loss:       -$185.00
Avg Trade Duration: 7.3 bars (H1)

=== QUALITY GATE RESULT: PASS ✅ ===
```

---

## Running Tests

### Unit tests (no MT5 required)
```bash
# All new spec009 unit tests
pytest tests/unit/test_pipeline.py tests/unit/test_backtest_engine.py \
       tests/unit/test_performance.py tests/unit/test_bar_monitor.py \
       tests/unit/test_data_loader.py tests/unit/test_position_simulator.py -v

# Coverage check
pytest tests/unit/ -k "pipeline or backtest or performance or bar_monitor or data_loader or position_simulator" \
       --cov=src/orchestrator --cov=src/backtest --cov-report=term-missing
```

### Full suite (all 6 modules)
```bash
pytest tests/unit/ -v
```

### Integration tests (no live MT5 required — uses mocked MT5)
```bash
pytest tests/integration/test_orchestrator_mocked.py tests/integration/test_backtest_full.py -v
```

---

## Config Reference

### New `backtest` section in `config.yaml`
```yaml
backtest:
  initial_balance: 10000.0      # USD starting equity for simulation
  spread_usd: 0.35              # Fixed spread (XAUUSD typical: 0.30–0.50)
  data_dir: "data/historical"   # Directory with XAUUSD_{TF}.csv files
  output_dir: "backtest/results"
  risk_percent: 1.0             # Risk per trade (% of balance)
```

### Existing sections (unchanged — all modules read their own sections)
- `analysis.atr` — ATR periods, adaptive multipliers (spec006)
- `filters` — session, spread, news, volatility thresholds (spec004)
- `risk` — max daily drawdown, risk percent (spec003)
- `execution` — activation/trailing distances, magic number (spec005)

---

## Key Invariants

- **ATR warm-up**: First 35 H1 bars of backtest are consumed for ATR history. No trades placed during warm-up.
- **Conservative SL/TP**: When both SL and TP trigger on same bar, SL is assumed hit first.
- **News filter in backtest**: Always ALLOWED (no historical news data — no events to block).
- **Determinism**: Same CSV input + same config always produces identical output. No random seeds needed.
- **No MT5 in backtest**: `src/backtest/` and `src/orchestrator/pipeline.py` have zero MT5 imports.
