# Research: Backtest Suite & Strategy Orchestrator

**Feature**: `009-backtest-orchestrator`  
**Date**: 2026-06-12  
**Status**: Complete — all decisions resolved

---

## D-001: Shared Pipeline Core Architecture

**Decision**: Implement `run_pipeline()` as a single pure function in `src/orchestrator/pipeline.py`, called identically by both the live orchestrator and the backtest engine.

**Rationale**: Spec FR-017 requires no code duplication between live and backtest pipeline logic. If signal detection or filter logic diverged between modes, backtests would not predict live performance. A single function eliminates this risk. The function receives all dependencies as parameters (ATRService, config, mode flag) — no global state.

**Alternatives considered**:
- Subclass-based pipeline (BasePipeline → LivePipeline + BacktestPipeline): Rejected — inheritance creates risk of accidental divergence when subclasses override methods
- Duplicate pipeline functions: Rejected — maintenance nightmare; spec FR-017 explicitly prohibits this

**Implementation note**: `mode: str = "live" | "backtest"` parameter controls: (a) whether `news_events=[]` is passed (backtest has no live news), (b) whether step 5 calls `ExecutionEngine.execute_signal()` or opens a `SimulatedPosition`. Pipeline stages 1-4 are completely identical in both modes.

---

## D-002: PipelineContext Dataclass

**Decision**: Use a single `PipelineContext` dataclass as the state container flowing through all pipeline stages.

**Rationale**: The existing codebase uses this pattern: `TradeGateResult` (spec004) and `TradeAuditEntry` (spec005) are dataclasses that accumulate state across a pipeline. `PipelineContext` extends this pattern to the full pipeline. Each stage mutates the context in place (or returns a new one — both acceptable; prefer mutation for simplicity). The caller (orchestrator or backtest engine) receives the fully-populated context and acts on `ctx.filter_result` and `ctx.risk_calc`.

**Fields**: `signal_id (str)`, `timeframe (Timeframe)`, `bars (dict[Timeframe, list[OHLCVBar]])`, `now_utc (datetime)`, `spread_usd (float)`, `news_events (list[NewsEvent])`, `atr_readings (dict[Timeframe, ATRReading])`, `entry_signal (Optional[EntrySignal])`, `filter_result (Optional[TradeGateResult])`, `risk_calc (Optional[RiskCalculation])`, `mode (str)`

---

## D-003: Bar Close Detection via Polling

**Decision**: Poll MT5 every 10 seconds using `mt5.copy_rates_from_pos("XAUUSD", TIMEFRAME_H1, 0, 2)` — compare `rates[-1]['time']` to `last_bar_time`. New bar detected when they differ.

**Rationale**: MT5 Python API (`MetaTrader5` package) does not provide async callbacks or event subscriptions for bar closes in Python. All production MT5 Python bots use the polling pattern. 10-second interval provides adequate responsiveness (bar closes every 3600 seconds for H1) while avoiding excessive API calls. Fetching 2 bars instead of 1 provides the previous close price for True Range calculation.

**Alternatives considered**:
- Tick-level monitoring: Rejected — H1 strategy does not need tick precision; excessive CPU usage
- MT5 Expert Advisor callback (MQL5): Rejected — would require separate MQL5 bot; Python is the primary language
- 1-second polling: Rejected — overkill for H1 strategy; 10 seconds is industry standard for H1 bots

**Recovery**: If `copy_rates_from_pos()` returns `None`, MT5 connection is lost. `bar_monitor.py` raises `MT5ConnectionError`. `StrategyOrchestrator` catches this, attempts reconnection with exponential backoff (1s, 2s, 4s, 8s, 16s — max 5 retries before halt).

---

## D-004: Conservative Backtest SL/TP Hit Rule

**Decision**: When both SL and TP prices are breached on the same bar (gap open or wide-range bar), assume SL is hit first. The trade records a loss rather than a profit.

**Rationale**: This is the standard conservative approach in retail backtesting. It prevents overfitting to historical data where wins look larger than they would be in live trading. The CLAUDE.md requirement "backtesting results: Win rate ≥ 50%, profit factor ≥ 1.5" must be met under conservative assumptions to be meaningful.

**Alternative considered**: Assume best case (TP hit first): Rejected — would overstate strategy performance; backtest would not predict live performance accurately.

**Implementation**: In `simulate_bar(position, bar)`:
```python
sl_breached = (bar.low <= position.sl_price if direction == LONG else bar.high >= position.sl_price)
tp2_breached = (bar.high >= position.tp2_price if direction == LONG else bar.low <= position.tp2_price)
if sl_breached and tp2_breached:
    # Conservative: SL hit first
    close_at = position.sl_price
```

---

## D-005: Backtest Spread = Fixed Config Value

**Decision**: Use `config['backtest']['spread_usd']` (default: 0.35 USD) as a fixed spread for all backtest trades. Not tick-by-tick simulated.

**Rationale**: XAUUSD H1 strategy performance is dominated by ATR-sized stops (typically 20-50 USD move). A 0.35 USD spread is <2% of the smallest stop. Tick-by-tick spread simulation requires tick data (not available from MT5 history export in standard format) and adds significant complexity for negligible accuracy improvement at H1 timeframe.

**Implementation**: Passed as `spread_usd` parameter to `evaluate_filters()` in backtest mode. Identical to live mode — `spread_filter.check_spread(spread_usd, config)` runs identically.

---

## D-006: News Filter Disabled in Backtest

**Decision**: Pass `news_events=[]` to `evaluate_filters()` in backtest mode. The news filter will always return ALLOWED because no upcoming events exist.

**Rationale**: No historical news calendar data source is integrated in spec009. The news filter in spec004 requires a list of `NewsEvent` objects with future timestamps — these don't exist for historical bars. Passing `[]` is the clean approach: the filter still runs, it just finds no events to block.

**Future enhancement (Phase 2)**: Integrate a historical news calendar CSV (e.g., Forex Factory calendar exports) to replay news blocks during backtesting.

---

## D-007: Signal Export as JSONL

**Decision**: Signal export file format is JSONL (JSON Lines) — one JSON object per line, one line per H1 bar evaluated.

**Rationale**: JSONL is the standard format for ML training data pipelines:
- Streamable: can process without loading entire file into memory
- Appendable: can add new data without rewriting the file
- Readable by pandas: `pd.read_json(path, lines=True)` 
- Schema-flexible: new fields can be added without breaking existing readers
- Human-readable: each line is valid JSON, easy to inspect

**Schema** (one row per bar):
```json
{
  "timestamp": "2024-01-15T10:00:00Z",
  "signal_type": "BOS_BULLISH",
  "confidence": 0.72,
  "filter_result": "BLOCKED",
  "filter_reason": "VOLATILITY_EXTREME",
  "direction": "LONG",
  "entry_price": null,
  "sl_price": null,
  "atr_h1_current": 12.5,
  "atr_h1_reference": 10.2,
  "volatility_ratio": 1.225,
  "volatility_regime": "NORMAL",
  "trade_placed": false
}
```

---

## D-008: ATR Warm-up Strategy

**Decision**: On live startup, fetch 150 bars per timeframe from MT5 history and pass to `ATRService.refresh()`. In backtest, the first 35 H1 bars are used for warm-up only (no trades placed during warm-up period).

**Rationale**: ATR needs `period=14` bars; reference ATR needs `reference_period=20` ATR values, which requires 20 × (14+1) = 300 bars in the naive case. However, since `ATRService` maintains a rolling `_atr_history` list, only `14 + 20 = 34` initial bars are actually needed to compute the first reference ATR. Fetching 150 bars provides comfortable headroom and costs <100ms from MT5 history.

**Backtest warm-up**: Skip the first `period + reference_period = 34` H1 bars from producing trades. During warm-up, `run_pipeline()` still calls `ATRService.refresh()` to build the ATR history, but `entry_signal.direction == NONE` (ATRService not ready → pipeline short-circuits before signal generation).

---

## D-009: Config Structure

**Decision**: New `backtest` section in `config.yaml`; no changes to existing sections.

**Rationale**: All existing modules read their own config sections. Adding a parallel `backtest` top-level section is consistent with the existing pattern: `filters`, `risk`, `execution`, `analysis` each own their section. The backtest section does not override live config — it is a separate namespace read only by `BacktestEngine` and `backtest_runner.py`.

```yaml
backtest:
  initial_balance: 10000.0
  spread_usd: 0.35
  data_dir: "data/historical"
  output_dir: "backtest/results"
  risk_percent: 1.0
```

---

## D-010: Entry Point Structure

**Decision**: `main.py` at repo root for live trading; `backtest_runner.py` at repo root for backtesting. Both are thin entry points that instantiate modules and delegate to `StrategyOrchestrator.run()` or `BacktestEngine.run()`.

**Rationale**: CLAUDE.md project structure shows `src/` for source code; root-level scripts are the convention for Python CLI entry points. Keeping `main.py` minimal (< 50 lines) follows the single-responsibility principle — all business logic lives in `src/`.

**`main.py` structure**:
```python
# Loads config → creates BrokerConnection + OrderManager + ATRService + ExecutionEngine
# → StrategyOrchestrator(broker, order_mgr, atr_svc, exec_engine, config)
# → orchestrator.run()
# Catches KeyboardInterrupt for clean shutdown
```

**`backtest_runner.py` structure**:
```python
# Loads config → creates BacktestEngine(config)
# → result = engine.run(data_dir=config['backtest']['data_dir'])
# → prints performance report + PASS/FAIL gates
# → saves result to config['backtest']['output_dir']
```
