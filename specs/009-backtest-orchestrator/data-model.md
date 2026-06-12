# Data Model: Backtest Suite & Strategy Orchestrator

**Feature**: `009-backtest-orchestrator`  
**Date**: 2026-06-12

---

## New Entities

### `PipelineContext`
Shared state container for one H1 bar's full pipeline evaluation. Flows through all stages of `run_pipeline()`. Fields are populated progressively — earlier stages populate inputs, later stages populate outputs.

```
PipelineContext
├── signal_id: str                          # UUID — unique per bar evaluation
├── timeframe: Timeframe                    # Always H1 for signal generation (M5/H4/D1 for ATR refresh only)
├── bars: dict[Timeframe, list[OHLCVBar]]   # Pre-fetched bars per timeframe (from caller)
├── now_utc: datetime                       # Bar close timestamp (UTC)
├── spread_usd: float                       # Current spread (live) or fixed config value (backtest)
├── news_events: list[NewsEvent]            # Upcoming news (live) or [] (backtest)
├── mode: str                               # "live" | "backtest"
│
├── atr_readings: dict[Timeframe, ATRReading]  # Populated by Stage 1 (ATR refresh)
├── entry_signal: Optional[EntrySignal]        # Populated by Stage 2 (SMC scoring)
├── filter_result: Optional[TradeGateResult]   # Populated by Stage 3 (filter gate)
└── risk_calc: Optional[RiskCalculation]       # Populated by Stage 4 (risk module)
```

**Validation rules**:
- `signal_id` must be non-empty string (UUID format preferred)
- `bars` must contain at least `Timeframe.H1` key with ≥ 2 bars
- `mode` must be exactly `"live"` or `"backtest"`
- Fields after Stage 2 remain `None` if pipeline short-circuits (e.g., ATR not ready, signal = NONE, filter = BLOCKED)

**State transitions**:
```
INIT → ATR_REFRESHED → SIGNAL_SCORED → FILTER_EVALUATED → RISK_CALCULATED → COMPLETE
                                            │
                                         BLOCKED (filter) → no risk calc → COMPLETE
                             │
                          SIGNAL_NONE (no SMC setup) → no filter/risk → COMPLETE
```

---

### `RiskCalculation`
*(Already exists in `src/risk/models.py` from spec003 — referenced here for completeness)*

```
RiskCalculation
├── lot_size: float
├── sl_price: float
├── tp1_price: float
├── tp2_price: float
├── sl_distance: float
├── risk_amount_usd: float
├── in_recovery: bool
└── reason: str
```

---

### `SimulatedPosition`
*(New — backtest only)* Represents one open hypothetical trade during backtest simulation.

```
SimulatedPosition
├── ticket: int                    # Sequential integer: 1, 2, 3, ...
├── direction: Direction           # LONG | SHORT
├── entry_price: float
├── entry_bar_idx: int             # Index in H1 bar list when trade opened
├── lot_size: float
├── sl_price: float                # Current SL (moves to breakeven after TP1)
├── tp1_price: float
├── tp2_price: float
├── is_tp1_hit: bool               # True after TP1 close — lot halved, SL → breakeven
├── is_closed: bool
└── pnl_usd: float                 # Accumulated P&L (updated on partial close and final close)
```

**Validation rules**:
- `entry_price > 0`, `lot_size > 0`
- `sl_price < entry_price` for LONG; `sl_price > entry_price` for SHORT
- `tp1_price > entry_price` for LONG; `tp1_price < entry_price` for SHORT
- `tp2_price > tp1_price` for LONG; `tp2_price < tp1_price` for SHORT

**State transitions**:
```
OPEN → TP1_HIT (lot halved, SL moves to breakeven) → TP2_HIT (CLOSED, profit)
     → SL_HIT (CLOSED, loss)
     → SL_HIT after TP1 (CLOSED, breakeven or small profit)
```

---

### `TradeRecord`
*(New)* Immutable record of one completed round-trip trade. Written to trade log; used for performance metrics.

```
TradeRecord
├── ticket: int
├── direction: Direction
├── entry_price: float
├── entry_time: datetime
├── exit_price: float
├── exit_time: datetime
├── exit_reason: str               # "SL_HIT" | "TP1_HIT" | "TP2_HIT" | "BREAKEVEN"
├── lot_size: float                # Final lot (may differ from entry if TP1 partial close)
├── pnl_usd: float                 # Positive = profit, negative = loss
├── duration_bars: int             # Number of H1 bars held
├── entry_signal_type: str         # e.g., "BOS_BULLISH + FVG + OB"
├── entry_confidence: float
└── filter_reason: str             # Always "ALLOWED" (blocked trades never open positions)
```

---

### `PerformanceMetrics`
*(New)* Computed from a completed list of `TradeRecord` + equity curve.

```
PerformanceMetrics
├── total_trades: int
├── winning_trades: int
├── losing_trades: int
├── win_rate_pct: float            # winning_trades / total_trades * 100
├── gross_profit_usd: float
├── gross_loss_usd: float
├── profit_factor: float           # gross_profit / abs(gross_loss); None if no losing trades
├── sharpe_ratio: float            # Annualised: mean(daily_returns) / std(daily_returns) * sqrt(252)
├── max_drawdown_pct: float        # Peak-to-trough as % of peak equity
├── max_drawdown_usd: float
├── avg_trade_duration_bars: float
├── largest_single_loss_usd: float
└── gate_results: dict[str, bool]  # {"win_rate_pass": True, "pf_pass": True, "dd_pass": False}
```

---

### `BacktestResult`
*(New)* Full output of one backtest run.

```
BacktestResult
├── config_snapshot: dict          # Copy of config used for this run (reproducibility)
├── data_period_start: datetime
├── data_period_end: datetime
├── warm_up_bars_skipped: int      # Always 35 (ATR warm-up)
├── total_bars_evaluated: int
├── trades: list[TradeRecord]
├── equity_curve: list[float]      # One entry per H1 bar (starting balance + cumulative P&L)
├── signal_log: list[dict]         # Raw signal export rows (before writing to JSONL)
├── metrics: PerformanceMetrics
└── output_paths: dict[str, str]   # {"report_json": ..., "signal_export_jsonl": ..., "trade_log_csv": ...}
```

---

### `BarEvent`
*(New — simple dataclass, used internally by StrategyOrchestrator)*

```
BarEvent
├── timeframe: Timeframe
├── bar: OHLCVBar                  # The newly closed bar
├── detected_at: datetime          # When the poll detected the new bar (UTC)
└── bars_fetched: dict[Timeframe, list[OHLCVBar]]  # 150-bar history for all timeframes
```

---

## Existing Entities (referenced, not modified)

| Entity | Location | Role in spec009 |
|--------|----------|-----------------|
| `OHLCVBar` | `src/analysis/models.py` | Input to pipeline — loaded from MT5 or CSV |
| `Timeframe` | `src/analysis/models.py` | H1/D1/H4/M5 constants for all bar fetches |
| `ATRReading` | `src/analysis/models.py` | Output of ATRService.refresh() — stored in PipelineContext |
| `EntrySignal` | `src/engine/models.py` | Output of score_and_assemble() — stored in PipelineContext |
| `TradeGateResult` | `src/filters/models.py` | Output of evaluate_filters() — stored in PipelineContext |
| `NewsEvent` | `src/filters/models.py` | Passed to evaluate_filters() — always [] in backtest |
| `ExecutionSignal` | `src/execution/models.py` | Built from EntrySignal + RiskCalculation for live mode |
| `TradeAuditEntry` | `src/execution/models.py` | Returned by ExecutionEngine.execute_signal() |
| `VolatilityRegime` | `src/analysis/models.py` | Derived from ATRReading.ratio; determines adaptive multipliers |

---

## File Storage

| Artifact | Path | Format | Consumer |
|----------|------|--------|---------|
| Historical OHLCV | `data/historical/XAUUSD_{TF}.csv` | CSV (date,time,open,high,low,close,volume) | `data_loader.py` |
| Signal export | `backtest/results/signals_{date}.jsonl` | JSONL | spec007 ML training |
| Trade log | `backtest/results/trades_{date}.csv` | CSV | Human review |
| Performance report | `backtest/results/report_{date}.json` | JSON | PASS/FAIL display |
| Live filter decisions | `logs/filter_decisions.json` | JSONL (existing) | Audit |
| Live audit log | `logs/trades.json` | JSONL (existing) | Audit |
