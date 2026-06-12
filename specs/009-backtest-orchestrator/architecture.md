# Shikra Trading System — Architecture

**Asset:** XAUUSD (Gold)  
**Strategy:** Smart Money Concepts (SMC)  
**Broker:** MetaTrader 5  
**Language:** Python 3.10+

---

## 1. System Overview

Shikra operates in two modes sharing a single evaluation pipeline:

```
┌─────────────────────────────────────────────────────────────┐
│                     ENTRY POINTS                            │
│                                                             │
│   main.py                    backtest_runner.py             │
│   (Live Trading)             (Historical Backtest)          │
└────────────┬────────────────────────┬───────────────────────┘
             │                        │
             ▼                        ▼
┌────────────────────┐    ┌───────────────────────┐
│ StrategyOrchestra- │    │   BacktestEngine       │
│ tor                │    │   (src/backtest/)      │
│ (src/orchestrator/)│    │                        │
│                    │    │  CSV Loader            │
│  Bar Monitor       │    │  Position Simulator    │
│  (MT5 polling)     │    │  Signal Exporter       │
│                    │    │  Performance Report    │
└────────┬───────────┘    └──────────┬────────────┘
         │                           │
         └──────────┬────────────────┘
                    │  SHARED
                    ▼
        ┌───────────────────────┐
        │    run_pipeline()     │
        │  (orchestrator/       │
        │   pipeline.py)        │
        │                       │
        │  Stage 1: ATR Refresh │
        │  Stage 2: SMC Detect  │
        │  Stage 3: Filters     │
        │  Stage 4: Risk Calc   │
        └───────────────────────┘
```

---

## 2. Module Map

```
src/
├── orchestrator/          # Live trading loop + shared pipeline
│   ├── strategy_orchestrator.py   ← Main live controller
│   ├── bar_monitor.py             ← H1 bar close detection (MT5 polling)
│   ├── pipeline.py                ← Shared 4-stage evaluation pipeline
│   └── models.py                  ← PipelineContext, BarEvent dataclasses
│
├── backtest/              # Historical replay engine
│   ├── backtest_engine.py         ← Bar-by-bar CSV replay
│   ├── data_loader.py             ← CSV → OHLCVBar[]
│   ├── position_simulator.py      ← SL/TP/TP1 simulation per bar
│   ├── signal_exporter.py         ← JSONL signal export
│   ├── performance.py             ← WR, PF, Sharpe, MaxDD metrics
│   └── models.py                  ← SimulatedPosition, TradeRecord,
│                                     PerformanceMetrics, BacktestResult
│
├── analysis/              # ATR calculation (volatility regime)
│   ├── atr_service.py             ← Per-timeframe ATR cache + refresh
│   ├── atr_calculator.py          ← 14-period Wilder ATR
│   ├── reference_atr.py           ← 20-period reference for ratio
│   ├── adaptive_multipliers.py    ← LOW/NORMAL/EXTREME regime multipliers
│   └── models.py                  ← OHLCVBar, Timeframe, ATRReading
│
├── engine/                # SMC signal detection (stateless)
│   ├── smc_engine.py              ← Top-level generate_signal() entry point
│   ├── bos_choch.py               ← Break of Structure / Change of Character
│   ├── fvg.py                     ← Fair Value Gap detection
│   ├── order_block.py             ← Order Block identification
│   ├── liquidity_sweep.py         ← Liquidity sweep detection
│   ├── swing.py                   ← Swing high/low (fractal-N)
│   ├── scorer.py                  ← Confidence score assembly (weights)
│   └── models.py                  ← EntrySignal, SignalType, Direction, Bias
│
├── filters/               # Pre-trade gate (4 filters in sequence)
│   ├── trade_gate.py              ← evaluate_filters() orchestrator
│   ├── session_filter.py          ← London/New York session check
│   ├── spread_filter.py           ← Max spread USD gate
│   ├── news_filter.py             ← High-impact event blackout
│   ├── volatility_filter.py       ← ATR ratio gate (LOW/EXTREME)
│   └── models.py                  ← TradeGateResult, FilterDecision, FilterResult
│
├── risk/                  # Position sizing + drawdown control
│   ├── risk_manager.py            ← Top-level risk coordinator
│   ├── lot_calculator.py          ← Lot size = Balance×Risk% / SL_pips
│   ├── drawdown_guard.py          ← Daily 5% drawdown circuit breaker
│   ├── trade_limits.py            ← Max trades/day, cooldown after SL
│   ├── recovery_mode.py           ← Reduced sizing after N consecutive losses
│   └── models.py                  ← RiskCalculation dataclass
│
├── execution/             # Order management + position tracking
│   ├── execution_engine.py        ← execute_signal(), manage_open_positions()
│   ├── preflight.py               ← run_preflight() — state checks before entry
│   ├── position_manager.py        ← Trailing SL, partial close at TP1
│   ├── kill_switch.py             ← Emergency halt (JSON file trigger)
│   ├── audit_logger.py            ← logs/trades.json append
│   └── models.py                  ← ExecutionSignal, PositionState, AuditAction
│
└── broker/                # MetaTrader 5 API wrapper
    ├── connection.py              ← connect(), disconnect(), status
    ├── market_data.py             ← fetch OHLCV bars, live tick price
    └── order_manager.py           ← send_order(), modify_sl()
```

---

## 3. Live Trading Data Flow

```
MT5 Terminal
     │
     │  10-sec poll
     ▼
bar_monitor.poll_for_new_bar()
     │
     │  New H1 bar detected
     │  Returns (True, bar_time, bars_dict[H1/H4/D1/M5])
     ▼
StrategyOrchestrator._on_new_bar()
     │
     ├─► kill_switch check ──► HALT if active
     │
     ├─► PipelineContext(
     │       mode="live",
     │       bars=bars_dict,       ← 150 bars per timeframe
     │       balance=current_equity,
     │       spread_usd=live_tick_spread,
     │       news_events=calendar,
     │   )
     │
     ▼
run_pipeline(ctx, atr_service, config)
     │
     │  Stage 1 ─── ATRService.refresh(tf, bars) × 4 timeframes
     │               → ATRReading(current_atr, reference_atr, regime)
     │               Short-circuit if H1 ATR not ready
     │
     │  Stage 2 ─── SMCEngine.generate_signal(h1_df, htf_bias)
     │               BOS/CHoCH + FVG + OB + LiquiditySweep + Scorer
     │               → EntrySignal(direction, confidence, signal_type,
     │                             entry_zone_top, entry_zone_bottom)
     │               Short-circuit if direction == NONE
     │
     │  Stage 3 ─── evaluate_filters(signal_id, now_utc, spread_usd, ...)
     │               session_filter → spread_filter → volatility_filter
     │               → news_filter (if mode=="live")
     │               → TradeGateResult(final_result=ALLOWED|BLOCKED)
     │               Short-circuit if BLOCKED
     │
     │  Stage 4 ─── calculate_sl_price() + calculate_tp_prices()
     │               + calculate_lot_size()
     │               → RiskCalculation(lot_size, sl_price, tp1, tp2)
     │
     ▼
ctx.filter_result == ALLOWED ?
     │
     ├─ NO  → log decision, no trade
     │
     └─ YES → ExecutionEngine.run_preflight()
                   ├─ kill_switch check
                   ├─ pyramiding check (1 open position max)
                   ├─ drawdown_guard (5% daily limit)
                   ├─ trade_limits (max N/day, cooldown after SL)
                   └─ margin / min_stop check
                         │
                         └─ PASS → OrderManager.send_order(BUY/SELL)
                                    MT5 fills order
                                    PositionState added to tracking dict
                                    AuditEntry written to logs/trades.json
```

---

## 4. Backtest Data Flow

```
backtest_runner.py
     │
     ▼
BacktestEngine(config).run()
     │
     ├─► _load_all_timeframes(data_dir)
     │       load_ohlcv_csv(dir, H1) → OHLCVBar[300]
     │       load_ohlcv_csv(dir, H4) → OHLCVBar[80]
     │       load_ohlcv_csv(dir, D1) → OHLCVBar[14]
     │       load_ohlcv_csv(dir, M5) → OHLCVBar[500]
     │
     ├─► WARM-UP (bars 0–34)
     │       ATRService.refresh() only — no pipeline, no trades
     │
     └─► MAIN LOOP (bars 35–N)
           │
           ├─► PipelineContext(mode="backtest", news_events=[])
           │
           ├─► run_pipeline()  ← SAME as live mode
           │
           ├─► simulate_bar(open_positions, h1_bar)
           │       SL hit?  → close, record loss
           │       TP1 hit? → halve lot, move SL to entry (breakeven)
           │       TP2 hit? → close, record profit
           │       Both SL+TP2? → SL wins (D-004 conservative rule)
           │
           ├─► Open new position if ALLOWED + risk_calc present
           │
           └─► Append balance to bar_equity[], bar_dates[]
     │
     ├─► export_signals(contexts, signals_{date}.jsonl)   ← 13 fields/row
     │
     ├─► compute_metrics(trades, bar_equity, initial_bal, bar_dates)
     │       Win Rate, Profit Factor, Sharpe (daily grouped ×√252),
     │       Max Drawdown (running peak), gate_results dict
     │
     ├─► _write_report_json()  → backtest/results/report_{date}.json
     ├─► _write_trades_csv()   → backtest/results/trades_{date}.csv
     │
     └─► BacktestResult(trades, equity_curve, metrics, output_paths)
```

---

## 5. Shared Pipeline — The Core Design Decision

Both live and backtest use the **identical** `run_pipeline()` function. Mode differences are confined to the caller:

| Concern | Live Mode | Backtest Mode |
|---------|-----------|---------------|
| Bar source | MT5 API (bar_monitor) | CSV file (data_loader) |
| News events | Loaded from calendar JSON | `[]` (disabled, FR-011) |
| Spread | Live tick spread | Fixed `config.backtest.spread_usd` |
| `ctx.mode` | `"live"` | `"backtest"` |
| Position mgmt | ExecutionEngine + MT5 | position_simulator (P&L simulation) |
| Risk preflight | `run_preflight()` (state checks) | Skipped in backtest |

`pipeline.py` contains zero `import MetaTrader5` statements — guaranteed by contract.

---

## 6. SMC Signal Detection — Internal Flow

```
generate_signal(h1_df, htf_bias, config)
         │
         ├─► detect_swing_points(df, fractal_n=2)
         │       → swing_highs[], swing_lows[]
         │
         ├─► detect_structure_break(df, swings)
         │       BOS  — price closes beyond last swing (trend continuation)
         │       CHoCH — price breaks opposing swing (reversal signal)
         │       → StructureBreak(type, direction, level, confidence)
         │
         ├─► detect_fvg_zones(df)
         │       3-candle gap where candle[i-1].high < candle[i+1].low (bullish)
         │       or candle[i-1].low > candle[i+1].high (bearish)
         │       → FVGZone[]
         │
         ├─► detect_order_blocks(df, swings)
         │       Last opposing candle before a BOS — institutional supply/demand
         │       → OrderBlock[]
         │
         ├─► detect_liquidity_sweeps(df, swings)
         │       Price wicks beyond swing level then reverses — stop hunt
         │       → LiquiditySweep[]
         │
         └─► score_and_assemble(structure, fvg, ob, sweep, htf_bias)
                 Weights: BOS/CHoCH=0.40, FVG=0.30, OB=0.20, Sweep=0.10
                 confidence = weighted sum (0.0–1.0)
                 → EntrySignal if confidence >= 0.65 else direction=NONE
```

---

## 7. Risk Management — Calculation Chain

```
D1 ATR (current) × sl_atr_multiplier (1.5)
     │
     ▼
SL Distance (pips)
     │
     ├─► SL Price = entry ± sl_distance  (direction-aware)
     │
     ├─► TP1 = entry + sl_distance × 1.5  (R:R 1.5)
     ├─► TP2 = entry + sl_distance × 3.0  (R:R 3.0)
     │
     └─► Lot Size = (Balance × 1%) / (sl_distance × pip_value_per_lot)
                    clamped to [min_lot=0.01, max_lot=5.0]

Daily Drawdown Guard:
     current_equity < day_start_equity × (1 - 0.05)
     → ALL trading halted for the day

Recovery Mode (after 3 consecutive losses):
     lot_size × 0.5  AND  confidence_threshold raised to 0.80
```

---

## 8. Execution & Position Lifecycle

```
ENTRY
  ExecutionSignal
       │
       ▼
  run_preflight()
  ├─ kill_switch?    → REJECTED
  ├─ pyramiding?     → REJECTED  (max 1 open position)
  ├─ daily drawdown? → REJECTED
  ├─ trade limits?   → REJECTED
  └─ margin / stop?  → REJECTED
       │ PASS
       ▼
  OrderManager.send_order()  ──► MT5 API
       │
       ▼
  PositionState added to execution_engine._open_positions{}

EACH BAR (manage_open_positions)
       │
       ├─► manage_positions(positions, current_price, tick)
       │       eval_trailing_stop()  → modify SL if +30 pips profit
       │       apply_partial_close() → close 50% at TP1, move SL to entry
       │
       └─► reconcile_positions()    → prune positions closed externally

EXIT
  SL/TP hit → MT5 closes position
  reconcile_positions() detects missing ticket
  AuditEntry(action=EXTERNALLY_CLOSED) written to logs/trades.json
```

---

## 9. Key Invariants

| # | Invariant |
|---|-----------|
| I-1 | `pipeline.py` has zero `import MetaTrader5` — testable without broker |
| I-2 | `src/backtest/` has zero MT5 imports — full replay without terminal |
| I-3 | `run_pipeline()` never raises — all exceptions caught and logged |
| I-4 | `generate_signal()` always returns a valid `EntrySignal` — never `None` |
| I-5 | SL wins when both SL and TP2 hit same bar (D-004 conservative rule) |
| I-6 | Daily drawdown enforced by `run_preflight()` only — not duplicated |
| I-7 | Risk % and all thresholds come from `config.yaml` — zero hardcoded values |
| I-8 | All trade decisions written to `logs/trades.json` with full audit context |

---

## 10. Directory Layout

```
forex-trading-bot/
├── main.py                    ← Live trading entry point
├── backtest_runner.py         ← Backtest CLI entry point
├── config.yaml                ← All configurable values
├── .env                       ← MT5 credentials (not committed)
│
├── src/                       ← All application code
│   ├── orchestrator/          ← Live loop + shared pipeline
│   ├── backtest/              ← Historical replay
│   ├── analysis/              ← ATR volatility service
│   ├── engine/                ← SMC signal detection
│   ├── filters/               ← Pre-trade gates
│   ├── risk/                  ← Position sizing + drawdown
│   ├── execution/             ← Order mgmt + audit
│   └── broker/                ← MT5 API wrapper
│
├── tests/
│   ├── unit/                  ← 430+ unit tests (≥80% coverage)
│   ├── integration/           ← 55+ integration tests
│   └── fixtures/              ← 300-row synthetic OHLCV CSVs
│
├── data/
│   └── historical/            ← OHLCV CSVs for backtest
│
├── backtest/
│   └── results/               ← report_*.json, signals_*.jsonl, trades_*.csv
│
├── logs/
│   ├── trades.json            ← Full audit trail
│   ├── kill_switch.json       ← Emergency halt trigger
│   └── filter_decisions.json  ← Filter rejection log
│
└── specs/                     ← Feature specs, tasks, checklists, ADRs
```
