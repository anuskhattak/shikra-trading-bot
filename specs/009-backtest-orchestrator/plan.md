# Implementation Plan: Backtest Suite & Strategy Orchestrator

**Branch**: `009-backtest-orchestrator` | **Date**: 2026-06-12 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/009-backtest-orchestrator/spec.md`

---

## Summary

Build `src/orchestrator/` and `src/backtest/` — the two remaining top-level modules that complete the Shikra trading system. The **Strategy Orchestrator** is the missing live trading loop: it connects to MT5, warms up data caches, detects new H1 bar closes by polling, and drives the full pipeline (ATR → SMC → filters → risk → execution) on each close. The **Backtest Engine** reuses the same pipeline core, replaces live MT5 calls with CSV historical data, simulates SL/TP hits bar-by-bar, and produces a performance report + signal export file for spec007 ML training. A single `PipelineContext` dataclass is the shared state container — populated by each pipeline stage and consumed identically by both modes.

---

## Technical Context

**Language/Version**: Python 3.10+  
**Primary Dependencies**: pandas (CSV loading, equity curve), numpy (Sharpe calculation), loguru (already present), pyyaml (already present), pytest + pytest-mock (already present) — one new dependency: `pandas`  
**Storage**: CSV files for historical OHLCV data; JSONL files for signal export and trade log; JSON for performance report  
**Testing**: pytest — orchestrator tests use mocked MT5 + mocked ATRService; backtest tests use fixed synthetic OHLCV CSV; no live MT5 required for any unit or integration test  
**Target Platform**: Windows (MT5 is Windows-only; orchestrator module imports MT5 but backtest module does not)  
**Project Type**: single  
**Performance Goals**: Full pipeline < 1 second per H1 bar close (SC-002); backtest of 2 years H1 data < 5 minutes (SC-003)  
**Constraints**: No MT5 imports in `src/backtest/` or `src/orchestrator/pipeline.py`; pipeline core must be identical for live and backtest (FR-017); backtest must be fully deterministic (SC-006, FR-015)

---

## Constitution Check

*GATE: Checked against CLAUDE.md core guarantees.*

| Guarantee | Requirement | Status |
|-----------|-------------|--------|
| Signal Integrity | Same SMC detection functions used in live and backtest — no special backtest signals | ✅ PASS — FR-010, FR-017; shared `run_pipeline()` function |
| Risk First | SL/TP calculated via `calculate_sl_price()` and `calculate_tp_prices()` before any order | ✅ PASS — FR-003; risk module called before `ExecutionEngine.execute_signal()` |
| Risk First | Backtest simulates SL hit conservatively (SL before TP if both triggered on same bar) | ✅ PASS — D-004; conservative simulation protects against overfitting |
| Risk First | Daily drawdown circuit breaker enforced in live orchestrator | ✅ PASS — FR-005; checked before every `execute_signal()` call |
| Auditability | Every pipeline decision logged with unique signal ID, timestamp, filter result | ✅ PASS — FR-006, FR-014; both live logs and backtest signal export |
| Quality Gates | Backtest performance report shows PASS/FAIL against Win ≥ 50%, PF ≥ 1.5, MaxDD < 30% | ✅ PASS — FR-013, SC-009; explicit gate evaluation in `BacktestResult` |
| Quality Gates | Unit test coverage ≥ 80% for pipeline core + backtest engine | ✅ PLANNED — SC-008; 6 unit test files covering all new modules |
| Documentation | Docstrings on all public functions explaining rule + why | ✅ ENFORCED — per CLAUDE.md Code Standards |

**Constitution result: PASS — all gates satisfied. No complexity violations.**

---

## Architecture

```
                         ┌──────────────────────────────────────────────────┐
                         │              SHARED PIPELINE CORE                │
                         │         src/orchestrator/pipeline.py             │
                         │                                                  │
                         │  run_pipeline(ctx, atr_service, config) ->      │
                         │      PipelineContext                             │
                         │                                                  │
                         │  Step 1: ATRService.refresh(tf, bars)            │
                         │  Step 2: score_and_assemble() → EntrySignal      │
                         │  Step 3: evaluate_filters() → TradeGateResult    │
                         │  Step 4: calculate_sl/tp/lot() → RiskCalculation │
                         │  Step 5: build ExecutionSignal (live) or         │
                         │          SimulatedPosition (backtest)            │
                         └──────────────────────────────────────────────────┘
                                    ↑                      ↑
             ┌─────────────────────┘                      └──────────────────────┐
             │                                                                    │
┌────────────────────────┐                                      ┌────────────────────────────┐
│  LIVE ORCHESTRATOR     │                                      │  BACKTEST ENGINE            │
│  src/orchestrator/     │                                      │  src/backtest/              │
│  strategy_orchestrator │                                      │  backtest_engine.py         │
│                        │                                      │                             │
│  1. Connect MT5        │                                      │  1. Load CSV → OHLCVBars    │
│  2. Warm up ATRService │                                      │  2. Replay bars chrono.     │
│  3. Poll bar closes    │                                      │  3. Simulate positions      │
│  4. run_pipeline()     │                                      │  4. run_pipeline()          │
│  5. ExecutionEngine    │                                      │  5. performance.compute()   │
│  6. manage_positions() │                                      │  6. Export signal JSONL     │
│  7. Clean shutdown     │                                      │  7. Export report JSON      │
└────────────────────────┘                                      └────────────────────────────┘
         │                                                                   │
         ▼                                                                   ▼
   main.py                                                        backtest_runner.py
(python main.py)                                       (python backtest_runner.py --data ...)
```

---

## Project Structure

### Documentation (this feature)

```text
specs/009-backtest-orchestrator/
├── plan.md              ← this file
├── research.md          ← all design decisions resolved
├── data-model.md        ← entities: PipelineContext, SimulatedPosition, BacktestResult, ...
├── quickstart.md        ← how to run live, how to run backtest, config reference
├── contracts/
│   ├── pipeline.md      ← run_pipeline() signature + stage contracts
│   └── backtest.md      ← BacktestEngine public API
└── tasks.md             ← Phase 2 (/sp.tasks — NOT created by /sp.plan)
```

### Source Code

```text
src/orchestrator/
├── __init__.py                   — public exports
├── strategy_orchestrator.py      — StrategyOrchestrator class (live trading loop)
├── bar_monitor.py                — poll_for_new_bar(): MT5 bar count polling
└── pipeline.py                   — run_pipeline(): shared core (no MT5 imports)

src/backtest/
├── __init__.py                   — public exports
├── backtest_engine.py            — BacktestEngine class (main controller)
├── data_loader.py                — load_ohlcv_csv(): CSV → dict[Timeframe, list[OHLCVBar]]
├── position_simulator.py         — SimulatedPosition; simulate_bar(): SL/TP hit detection
├── performance.py                — compute_metrics(): Win%, PF, Sharpe, MaxDD
└── signal_exporter.py            — export_signals(): PipelineContext list → JSONL

main.py                           — entry point: python main.py [--config config.yaml]
backtest_runner.py                — CLI: python backtest_runner.py --data data/historical/

data/
└── historical/                   — OHLCV CSV files (one per timeframe)
    ├── XAUUSD_H1.csv
    ├── XAUUSD_D1.csv
    ├── XAUUSD_H4.csv
    └── XAUUSD_M5.csv

tests/unit/
├── test_pipeline.py              — run_pipeline() with mocked modules
├── test_backtest_engine.py       — BacktestEngine full-loop with synthetic data
├── test_performance.py           — compute_metrics() hand-calculated assertions
├── test_bar_monitor.py           — poll_for_new_bar() with mocked MT5
├── test_data_loader.py           — CSV parsing + OHLCVBar conversion
└── test_position_simulator.py    — SL/TP hit detection for all scenarios

tests/integration/
├── test_backtest_full.py         — full backtest run on 6-month synthetic dataset
└── test_orchestrator_mocked.py   — orchestrator loop with mocked MT5 + mocked modules
```

**Structure Decision**: Two new top-level source modules (`orchestrator`, `backtest`). The pipeline core lives in `orchestrator/pipeline.py` (not `backtest/`) because live trading is primary — backtest imports from orchestrator, not the other way around. Entry points (`main.py`, `backtest_runner.py`) live at repo root to match CLAUDE.md project structure.

---

## Key Design Decisions

### D-001: Shared Pipeline Core (`pipeline.py`)
`run_pipeline(ctx: PipelineContext, atr_service: ATRService, config: dict) -> PipelineContext` is a pure function (no MT5 imports, no side effects except logging). Both `StrategyOrchestrator` and `BacktestEngine` call it identically. This ensures the same signal logic produces identical decisions regardless of mode (FR-017). See `research.md` D-001.

### D-002: `PipelineContext` as Pipeline State Container
A single dataclass holds all pipeline state for one bar evaluation: input bar data, ATR readings, SMC signal, filter result, risk calc, and execution outcome. Each pipeline stage mutates the context in place. This pattern matches `TradeGateResult` (spec004) and `TradeAuditEntry` (spec005). See `research.md` D-002.

### D-003: Bar Close Detection via Polling
`bar_monitor.py` polls MT5 every 10 seconds using `mt5.copy_rates_from_pos("XAUUSD", MT5_TIMEFRAME_H1, 0, 1)` and compares the most recent bar's `time` field to the last-seen bar time. When they differ, a new H1 bar has closed. This is the standard pattern for MT5 Python bots — the Python API does not offer async callbacks. See `research.md` D-003.

### D-004: Conservative Backtest SL/TP Hit Rule
When both SL and TP are triggered on the same bar (gap open, high volatility bar), assume SL is hit first. This is conservative and prevents backtest overfitting — better to understate performance than overstate it. See `research.md` D-004.

### D-005: Backtest Spread = Fixed Config Value
Spread is set once from `config.backtest.spread_usd` (default: 0.35 USD for XAUUSD). No tick-by-tick spread simulation — acceptable approximation for H1 strategy where spread is a minor factor. See `research.md` D-005.

### D-006: News Filter Disabled in Backtest
No historical news event data source is available in Phase 1. The news filter is bypassed in `run_pipeline()` when `mode == "backtest"` — `news_events=[]` is passed, which means the news filter always returns ALLOWED. This is documented in Assumptions and flagged as a Phase 2 enhancement. See `research.md` D-006.

### D-007: Signal Export as JSONL
One JSON object per line, one line per bar evaluated. Schema matches spec007 ML feature requirements: timestamp, timeframe, signal_type, confidence, filter_result, direction, entry_price (null if blocked). JSONL is streamable, appendable, and directly readable by pandas `read_json(lines=True)`. See `research.md` D-007.

### D-008: ATR Warm-up from MT5 History on Startup
On live startup, `StrategyOrchestrator` fetches 150 H1 bars, 150 D1 bars, 150 H4 bars, and 500 M5 bars from MT5 history. Passes each to `ATRService.refresh()`. 150 bars covers 14-period ATR + 20-period reference ATR with comfortable margin. M5 uses more bars due to faster timeframe. See `research.md` D-008.

### D-009: `config.yaml` `backtest` Section
New section parallel to existing `analysis`, `filters`, `risk`, `execution`. Contains: `initial_balance`, `spread_usd`, `data_dir`, `output_dir`, `risk_percent` (can differ from live for backtesting sensitivity). See `research.md` D-009.

### D-010: `main.py` as Live Entry Point
Single file at repo root. Reads `config.yaml`, instantiates `BrokerConnection + OrderManager + ATRService + ExecutionEngine`, hands to `StrategyOrchestrator`, and calls `orchestrator.run()`. Catches `KeyboardInterrupt` for clean shutdown. `backtest_runner.py` follows same pattern for backtest mode. See `research.md` D-010.

---

## Module Breakdown

### `src/orchestrator/pipeline.py` (shared core — no MT5)
- `run_pipeline(ctx: PipelineContext, atr_service: ATRService, config: dict, mode: str = "live") -> PipelineContext`
  - Stage 1: `ATRService.refresh(ctx.timeframe, ctx.bars[ctx.timeframe])`
  - Stage 2: Detect structure break → `score_and_assemble()` → `ctx.entry_signal`
  - Stage 3: `evaluate_filters(ctx.signal_id, ctx.now_utc, spread_usd, news_events, current_atr, reference_atr, config)` → `ctx.filter_result`
  - Stage 4 (if ALLOWED): `calculate_sl_price() + calculate_tp_prices() + calculate_lot_size()` → `ctx.risk_calc`
  - Stage 5: returns populated `PipelineContext` — caller decides what to do with it (place order vs. simulate)

### `src/orchestrator/bar_monitor.py`
- `poll_for_new_bar(last_bar_time: datetime, symbol: str, timeframe) -> tuple[bool, datetime, list[OHLCVBar]]`
  - Returns `(is_new_bar, new_bar_time, recent_bars)` — fetches 150 bars if new bar detected
  - Polls using `mt5.copy_rates_from_pos()` — raises `MT5ConnectionError` if terminal disconnected

### `src/orchestrator/strategy_orchestrator.py`
- `StrategyOrchestrator.__init__(broker, order_manager, atr_service, execution_engine, config)`
- `StrategyOrchestrator.run() -> None` — main loop; runs until kill switch or KeyboardInterrupt
- `StrategyOrchestrator._startup() -> None` — connect, load history, warm up ATRService
- `StrategyOrchestrator._on_new_bar(bar_event) -> None` — call `run_pipeline()`, then `execution_engine.execute_signal()`
- `StrategyOrchestrator._shutdown() -> None` — disconnect, log session summary

### `src/backtest/data_loader.py`
- `load_ohlcv_csv(data_dir: str, timeframe: Timeframe) -> list[OHLCVBar]`
  - Reads `{data_dir}/XAUUSD_{timeframe}.csv` with columns: `time, open, high, low, close, volume`
  - Returns oldest-first list of `OHLCVBar`

### `src/backtest/position_simulator.py`
- `SimulatedPosition` dataclass: `ticket, direction, entry_price, sl_price, tp1_price, tp2_price, lot_size, entry_bar_idx, is_tp1_hit, is_closed, pnl_usd`
- `simulate_bar(position: SimulatedPosition, bar: OHLCVBar) -> tuple[SimulatedPosition, Optional[TradeRecord]]`
  - SL hit: close at `sl_price`, return `TradeRecord` with negative P&L
  - TP1 hit (not yet): halve lot, set `sl_price = entry_price` (breakeven)
  - TP2 hit: close remaining lot at `tp2_price`, return `TradeRecord` with positive P&L
  - Both SL + TP same bar: SL hit first (conservative — D-004)

### `src/backtest/performance.py`
- `compute_metrics(trades: list[TradeRecord], equity_curve: list[float]) -> PerformanceMetrics`
  - `win_rate = wins / total_trades * 100`
  - `profit_factor = gross_profit / gross_loss` (∞ if no losing trades)
  - `sharpe_ratio`: compute daily P&L from equity curve; annualize = mean(daily) / std(daily) * sqrt(252)
  - `max_drawdown_pct`: peak-to-trough of equity curve as % of peak equity

### `src/backtest/signal_exporter.py`
- `export_signals(contexts: list[PipelineContext], output_path: str) -> None`
  - Writes JSONL: one JSON object per bar evaluated
  - Fields: `timestamp, signal_type, confidence, filter_result, filter_reason, direction, entry_price, sl_price, atr_current, atr_reference, volatility_ratio`

### `src/backtest/backtest_engine.py`
- `BacktestEngine.__init__(config: dict)`
- `BacktestEngine.run(data_dir: str) -> BacktestResult`
  - Load all timeframe CSVs → `dict[Timeframe, list[OHLCVBar]]`
  - Replay H1 bars chronologically: call `run_pipeline()` with `mode="backtest"`
  - On ALLOWED signal: open `SimulatedPosition`
  - Each bar: `simulate_bar()` for all open positions
  - After all bars: `compute_metrics()`, `export_signals()`, return `BacktestResult`

---

## Integration Points with Existing Modules

| This module calls | Target module | Method | Purpose |
|-------------------|---------------|--------|---------|
| `pipeline.py` | `src/analysis/atr_service.py` | `ATRService.refresh(tf, bars)` | ATR computation per bar close |
| `pipeline.py` | `src/engine/bos_choch.py` | `detect_structure_break()` | SMC signal detection |
| `pipeline.py` | `src/engine/fvg.py` | `detect_fvg_zones()` | FVG zone detection |
| `pipeline.py` | `src/engine/order_block.py` | `detect_order_blocks()` | OB detection |
| `pipeline.py` | `src/engine/liquidity_sweep.py` | `detect_liquidity_sweeps()` | LS detection |
| `pipeline.py` | `src/engine/scorer.py` | `score_and_assemble()` | EntrySignal assembly |
| `pipeline.py` | `src/filters/trade_gate.py` | `evaluate_filters()` | Pre-trade gate |
| `pipeline.py` | `src/risk/lot_calculator.py` | `calculate_sl_price()`, `calculate_tp_prices()`, `calculate_lot_size()` | Risk parameters |
| `strategy_orchestrator.py` | `src/execution/execution_engine.py` | `ExecutionEngine.execute_signal()` | Live order placement |
| `strategy_orchestrator.py` | `src/execution/execution_engine.py` | `ExecutionEngine.manage_open_positions()` | Trailing stop management |
| `bar_monitor.py` | MT5 API | `mt5.copy_rates_from_pos()` | Bar close detection |

---

## Config Changes Required

Add `backtest` section to `config.yaml`:

```yaml
backtest:
  initial_balance: 10000.0     # USD, starting equity for simulation
  spread_usd: 0.35             # Fixed spread (XAUUSD typical: 0.30–0.50 USD)
  data_dir: "data/historical"  # Directory containing XAUUSD_{TF}.csv files
  output_dir: "backtest/results"
  risk_percent: 1.0            # % of balance risked per trade (same as live default)
```

No changes to existing config sections — all current module configs remain intact.

---

## Complexity Tracking

> No constitution violations. Complexity table not required.

---

## Risks

1. **MT5 bar polling timing**: 10-second polling may occasionally miss a bar close at exactly the turn. Mitigation: always fetch the last 2 bars and compare timestamps; if `time[-1] != last_seen_time`, process the new bar. This is industry-standard for MT5 Python bots.

2. **Backtest ATR warm-up**: The first 14 H1 bars of the backtest dataset cannot produce ATR. Mitigation: `data_loader` must load at least `period + reference_period + 1 = 35` bars before the first tradeable bar. `BacktestEngine` skips the first 35 bars as warm-up (no trades placed, ATR history built).

3. **Sharpe Ratio with zero trades**: `std(daily_returns) == 0` if no trades. Mitigation: return `sharpe_ratio = 0.0` when no trades exist; document in report.
