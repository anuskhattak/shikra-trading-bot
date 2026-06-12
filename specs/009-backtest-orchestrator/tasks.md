# Tasks: Backtest Suite & Strategy Orchestrator

**Input**: Design documents from `/specs/009-backtest-orchestrator/`  
**Branch**: `009-backtest-orchestrator`  
**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/ ✅

**Tests**: Included — spec SC-008 requires ≥ 80% unit test coverage for `src/orchestrator/` and `src/backtest/`.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared state)
- **[US#]**: Maps to user story in spec.md

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create module directories, configure new dependency, update config, and establish data/output directories.

- [x] T001 Create `src/orchestrator/__init__.py` and `src/backtest/__init__.py` as empty placeholders (both directories new)
- [x] T002 Verify `pandas` is available: add to `requirements.txt` if not present (plan: one new dependency)
- [x] T003 [P] Add `backtest` config section to `config.yaml` with defaults: `initial_balance: 10000.0`, `spread_usd: 0.35`, `data_dir: "data/historical"`, `output_dir: "backtest/results"`, `risk_percent: 1.0`; also add `orchestrator` section: `max_reconnect_retries: 5`, `reconnect_backoff_base_seconds: 1` (FR-008: retries must be configurable)
- [x] T004 [P] Create `data/historical/` and `backtest/results/` directories (add `.gitkeep` to each so directories are tracked)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared pipeline infrastructure used by BOTH live orchestrator (US1) and backtest engine (US2). Must be complete before either user story begins.

**⚠️ CRITICAL**: No US1 or US2 work can begin until this phase is complete.

- [x] T005 Implement `PipelineContext` and `BarEvent` dataclasses in `src/orchestrator/models.py`:
  - `PipelineContext`: `signal_id: str`, `timeframe: Timeframe`, `bars: dict[Timeframe, list[OHLCVBar]]`, `now_utc: datetime`, `spread_usd: float`, `news_events: list[NewsEvent]`, `mode: str` ("live"|"backtest"); output fields defaulting to None/empty: `atr_readings: dict`, `entry_signal: Optional[EntrySignal]`, `filter_result: Optional[TradeGateResult]`, `risk_calc: Optional[RiskCalculation]`
  - `BarEvent`: `timeframe: Timeframe`, `bar: OHLCVBar`, `detected_at: datetime`, `bars_fetched: dict[Timeframe, list[OHLCVBar]]` (used by StrategyOrchestrator to pass bar data into `_on_new_bar`)
- [x] T006 Implement `run_pipeline(ctx: PipelineContext, atr_service: ATRService, config: dict) -> PipelineContext` in `src/orchestrator/pipeline.py` — 4 sequential stages: (1) ATR refresh for all timeframes in ctx.bars, (2) SMC detection via detect_structure_break + detect_fvg_zones + detect_order_blocks + detect_liquidity_sweeps + score_and_assemble → ctx.entry_signal, (3) evaluate_filters → ctx.filter_result (short-circuit if BLOCKED), (4) calculate_sl_price + calculate_tp_prices + calculate_lot_size → ctx.risk_calc (only if ALLOWED). No MT5 imports. All exceptions caught and logged — never raises.
- [x] T007 Write `tests/unit/test_pipeline.py` — 5 tests: (1) full ALLOWED path: ATR ready + signal detected + filter ALLOWED + risk_calc populated, (2) filter BLOCKED: risk_calc is None (short-circuit), (3) ATR not ready: entry_signal is None (short-circuit before SMC), (4) NONE signal: filter not called (short-circuit before filters), (5) exception in ATR stage → graceful return, ctx not crashed

**Checkpoint**: Foundation ready — `run_pipeline()` functional; both US1 and US2 can now proceed independently.

---

## Phase 3: User Story 1 — Live Strategy Orchestrator (Priority: P1) 🎯 MVP

**Goal**: A running `python main.py` that connects to MT5, warms up ATR data, polls for H1 bar closes, and executes the full pipeline per bar.

**Independent Test**: `pytest tests/unit/test_bar_monitor.py tests/integration/test_orchestrator_mocked.py -v` passes. Orchestrator starts, processes a synthetic bar event, and calls `execute_signal()` for an ALLOWED signal — all with mocked MT5.

- [x] T008 [US1] Implement `poll_for_new_bar(last_bar_time, symbol, timeframe_mt5, fetch_count=150) -> tuple[bool, datetime, dict[Timeframe, list[OHLCVBar]]]` in `src/orchestrator/bar_monitor.py` — uses `mt5.copy_rates_from_pos()` to fetch 2 bars; compares `rates[-1]['time']` (datetime) to `last_bar_time`; if different: fetch 150 bars for all 4 timeframes and return (True, new_time, bars_dict); raises `MT5ConnectionError` (custom exception in same file) if MT5 returns None
- [x] T009 [US1] Write `tests/unit/test_bar_monitor.py` — 4 tests: (1) new bar detected (mocked MT5 returns different time), (2) no new bar (same time → returns False, empty dict), (3) MT5 returns None → raises MT5ConnectionError, (4) first call with `last_bar_time=None` → always returns True with bars
- [x] T010 [US1] Implement `StrategyOrchestrator` class in `src/orchestrator/strategy_orchestrator.py`:
  - `__init__(broker, order_manager, atr_service, execution_engine, config, kill_switch_path)` — store all deps; `_last_bar_time = None`; `_session_trades = 0`; `_session_start = None`
  - `_startup()` — `broker.connect()`; fetch 150 bars per timeframe via `market_data`; call `atr_service.refresh(tf, bars)` for all 4 timeframes; log "ready"
  - `run()` — loop: `time.sleep(10)`; `poll_for_new_bar()`; on new bar: `_on_new_bar(bar_event)`; handle `KeyboardInterrupt` → `_shutdown()`; handle `MT5ConnectionError` → reconnect with exponential backoff using `config['orchestrator']['reconnect_backoff_base_seconds']` × 2^attempt, up to `config['orchestrator']['max_reconnect_retries']` attempts before halting
  - `_on_new_bar(bars_dict, new_bar_time)` — set `ctx.now_utc = new_bar_time` (bar close timestamp, not system clock — for determinism and accurate session filter); build `PipelineContext`; `run_pipeline(ctx, atr_service, config)`; if `ctx.filter_result is not None and ctx.filter_result.final_result == FilterResult.ALLOWED` and `ctx.risk_calc` is not None: build `ExecutionSignal` → `execution_engine.execute_signal(signal, day_start_equity, current_equity)` — daily drawdown is already enforced by ExecutionEngine.run_preflight() (spec005); do NOT duplicate drawdown check here; fetch `current_price = mt5.symbol_info_tick("XAUUSD").last` then call `execution_engine.manage_open_positions(current_price)`
  - `_shutdown()` — `broker.disconnect()`; log session summary (trades placed, runtime)
- [x] T011 [US1] Write `tests/integration/test_orchestrator_mocked.py` — 5 tests using mocked MT5 + mocked modules: (1) `_startup()` connects broker and calls ATRService.refresh × 4 timeframes, (2) `_on_new_bar()` with ALLOWED signal calls execute_signal once, (3) `_on_new_bar()` with BLOCKED signal does NOT call execute_signal, (4) kill switch active → execute_signal not called but manage_open_positions IS called, (5) MT5ConnectionError raised during polling → orchestrator retries up to `max_reconnect_retries` times → on success resumes; on exhausted retries → raises SystemExit (FR-008, SC-007)
- [x] T012 [US1] Implement `main.py` at repo root — load `config.yaml` with PyYAML; create `BrokerConnection(account, password, server)` from env vars or config; `OrderManager(magic_number=config['execution']['magic_number'])`; `ATRService(config)`; `ExecutionEngine(order_manager, config, kill_switch_path=Path("logs/kill_switch.json"))`; `StrategyOrchestrator(broker, order_manager, atr_svc, exec_engine, config)`; call `orchestrator.run()`; catch `KeyboardInterrupt` with clean log message

**Checkpoint**: US1 complete — `python main.py` produces a running live trading loop. All US1 tests pass independently.

---

## Phase 4: User Story 2 — Backtest Engine (Priority: P1)

**Goal**: `python backtest_runner.py` replays historical OHLCV CSV data through the same pipeline and produces a signal export JSONL and trade log.

**Independent Test**: `pytest tests/unit/test_data_loader.py tests/unit/test_position_simulator.py tests/integration/test_backtest_full.py -v` passes. BacktestEngine processes 6 months of synthetic H1 data: ≥ 1 trade placed, equity curve populated, signal JSONL written, deterministic (run twice → same output).

- [x] T013 [US2] Implement `SimulatedPosition` and `TradeRecord` dataclasses in `src/backtest/models.py`:
  - `SimulatedPosition`: `ticket: int`, `direction: Direction`, `entry_price: float`, `entry_bar_idx: int`, `lot_size: float`, `sl_price: float`, `tp1_price: float`, `tp2_price: float`, `is_tp1_hit: bool = False`, `is_closed: bool = False`, `pnl_usd: float = 0.0`
  - `TradeRecord`: `ticket: int`, `direction: Direction`, `entry_price: float`, `entry_time: datetime`, `exit_price: float`, `exit_time: datetime`, `exit_reason: str`, `lot_size: float`, `pnl_usd: float`, `duration_bars: int`, `entry_signal_type: str`, `entry_confidence: float`
- [x] T014 [US2] Write `tests/unit/test_backtest_models.py` — 6 tests: SimulatedPosition instantiation with defaults, SimulatedPosition field validation (sl < entry for LONG), TradeRecord immutability (frozen=True or documented as not mutated after creation), TradeRecord pnl sign convention (positive = profit), Direction values match src/engine/models.py Direction enum
- [x] T015 [US2] Implement `load_ohlcv_csv(data_dir, timeframe, symbol="XAUUSD") -> list[OHLCVBar]` in `src/backtest/data_loader.py` — reads `{data_dir}/{symbol}_{timeframe.name}.csv`; expected columns: `date` (YYYY-MM-DD), `time` (HH:MM), `open`, `high`, `low`, `close`, `volume` (case-insensitive); parses `datetime` from date+time columns; returns `list[OHLCVBar]` sorted oldest-first; raises `FileNotFoundError` if file missing, `ValueError` if required columns absent
- [x] T016 [US2] Write `tests/unit/test_data_loader.py` — 5 tests: valid CSV with 100 rows → 100 OHLCVBars oldest-first, missing file → FileNotFoundError, missing column → ValueError, OHLCVBar fields correctly mapped (open/high/low/close/volume/timestamp), extra CSV columns silently ignored
- [x] T017 [US2] Implement `simulate_bar(position: SimulatedPosition, bar: OHLCVBar) -> tuple[SimulatedPosition, Optional[TradeRecord]]` in `src/backtest/position_simulator.py` — LONG: SL hit if `bar.low <= sl_price`, TP2 hit if `bar.high >= tp2_price`, TP1 hit if `bar.high >= tp1_price`; SHORT: reverse comparisons; TP1 logic: halve `lot_size`, set `sl_price = entry_price`, set `is_tp1_hit = True`, return None (still open); SL close: `pnl_usd = (sl_price - entry_price) × direction_sign × lot_size × XAUUSD_PIP_VALUE`; if both SL + TP2 same bar: SL wins (D-004)
- [x] T018 [US2] Write `tests/unit/test_position_simulator.py` — 8 tests: (1) LONG SL hit → TradeRecord with negative P&L, (2) LONG TP2 hit → TradeRecord with positive P&L, (3) LONG TP1 hit → position updated (tp1_hit=True, sl=entry), TradeRecord=None, (4) LONG SL hit after TP1 → breakeven TradeRecord, (5) LONG both SL+TP same bar → SL wins (loss), (6) SHORT SL hit → negative P&L, (7) SHORT TP2 hit → positive P&L, (8) bar does not touch any price → position unchanged, None returned
- [x] T019 [US2] Implement `export_signals(contexts: list[PipelineContext], output_path: str) -> None` in `src/backtest/signal_exporter.py` — writes JSONL (one JSON per line) with fields per PipelineContext: `timestamp` (now_utc ISO), `signal_type` (entry_signal.signal_type.value or "NONE"), `confidence` (entry_signal.confidence or 0.0), `filter_result` ("ALLOWED"|"BLOCKED"|"N/A"), `filter_reason` (first blocked decision reason or ""), `direction` (entry_signal.direction.value or "NONE"), `entry_price` (null if no trade), `sl_price` (null if no trade), `atr_h1_current` (from atr_readings[H1].current_atr or null), `atr_h1_reference` (from atr_readings[H1].reference_atr or null), `volatility_ratio` (from atr_readings[H1].ratio or null), `volatility_regime` (from VolatilityRegime classification or null), `trade_placed` (bool: risk_calc is not None and filter ALLOWED)
- [x] T020 [US2] Implement `BacktestEngine` class in `src/backtest/backtest_engine.py`:
  - `__init__(config: dict)` — validates `config['backtest']` exists; creates internal `ATRService(config)` (isolated instance); sets `initial_balance = config['backtest']['initial_balance']`; sets `spread_usd = config['backtest']['spread_usd']`
  - `run(data_dir=None) -> BacktestResult` — load H1, D1, H4, M5 CSVs via `load_ohlcv_csv()`; validate H1 len ≥ 35; initialize equity = initial_balance, open_positions = [], all_trades = [], equity_curve = []; skip first 35 H1 bars (warm-up: call ATRService.refresh but no trades); for each remaining H1 bar: build PipelineContext (mode="backtest", news_events=[], spread_usd from config); call `run_pipeline(ctx, atr_service, config)`; if ALLOWED: open SimulatedPosition (ticket=len(all_trades)+1); for all open positions: `simulate_bar(pos, bar)` → collect closed TradeRecords; update equity_curve; collect ctx in signal_log; after all bars: `export_signals(signal_log, output_path)`; write trade CSV; return `BacktestResult`
- [x] T021 [US2] Write `tests/integration/test_backtest_full.py` — 3 tests using synthetic 200-bar H1/D1/H4/M5 CSVs (generated in test fixtures): (1) full run completes without error and returns BacktestResult with trades list and equity_curve of len ≥ 165 (200 - 35 warm-up), (2) signal JSONL file written to output_dir, (3) determinism: run twice with identical config → identical list of TradeRecord.pnl_usd values

**Checkpoint**: US2 complete — `BacktestEngine.run()` produces trade log and signal export. All US2 tests pass independently.

---

## Phase 5: User Story 3 — Backtest Performance Report (Priority: P2)

**Goal**: `python backtest_runner.py` prints a formatted performance report with Win%, Profit Factor, Sharpe, Max Drawdown, and explicit PASS/FAIL against quality gates (Win ≥ 50%, PF ≥ 1.5, MaxDD < 30%).

**Independent Test**: `pytest tests/unit/test_performance.py -v` passes. Hand-calculated 10-trade scenario matches computed metrics within ±0.1%. PASS/FAIL gates correctly evaluated.

- [x] T022 [US3] Add `PerformanceMetrics` and `BacktestResult` dataclasses to `src/backtest/models.py`:
  - `PerformanceMetrics`: `total_trades: int`, `winning_trades: int`, `losing_trades: int`, `win_rate_pct: float`, `gross_profit_usd: float`, `gross_loss_usd: float`, `profit_factor: float`, `sharpe_ratio: float`, `max_drawdown_pct: float`, `max_drawdown_usd: float`, `avg_trade_duration_bars: float`, `largest_single_loss_usd: float`, `gate_results: dict[str, bool]`
  - `BacktestResult`: `config_snapshot: dict`, `data_period_start: Optional[datetime]`, `data_period_end: Optional[datetime]`, `warm_up_bars_skipped: int`, `total_bars_evaluated: int`, `trades: list[TradeRecord]`, `equity_curve: list[float]`, `metrics: Optional[PerformanceMetrics]`, `output_paths: dict[str, str]`
- [x] T023 [US3] Implement `compute_metrics(trades: list[TradeRecord], equity_curve: list[float], initial_balance: float) -> PerformanceMetrics` in `src/backtest/performance.py`:
  - `win_rate_pct = (winning_trades / total_trades * 100)` — 0.0 if no trades
  - `profit_factor = gross_profit / abs(gross_loss)` — `float('inf')` if no losing trades, `0.0` if no winning trades
  - `sharpe_ratio`: `compute_metrics` receives a `bar_dates: list[date]` parallel to `equity_curve` (one date per H1 bar, added to BacktestEngine output in T025); group equity_curve values by calendar date using `bar_dates`; `daily_equity[date] = equity_curve[-1 index of that date]` (last H1 bar equity per day); `daily_return[i] = (daily_equity[i] - daily_equity[i-1]) / daily_equity[i-1]`; `sharpe = mean(daily_returns) / std(daily_returns) * sqrt(252)`; return 0.0 if std == 0 or fewer than 2 trading days
  - `max_drawdown_pct`: iterate equity_curve tracking running peak; `drawdown = (peak - current) / peak * 100`; track max
  - `gate_results = {"win_rate_pass": win_rate_pct >= 50.0, "pf_pass": profit_factor >= 1.5, "dd_pass": max_drawdown_pct < 30.0}`
- [x] T024 [US3] Write `tests/unit/test_performance.py` — 6 tests: (1) hand-calculated 10-trade scenario (6 wins @ +$100 each, 4 losses @ -$80 each → Win=60%, PF=1.875, verify ±0.1%), (2) zero trades → all metrics 0.0 / 0 / inf as appropriate, (3) no losing trades → profit_factor = float('inf'), (4) std of returns = 0 → sharpe = 0.0, (5) PASS/FAIL gates: win_rate=55%, PF=1.6, MaxDD=20% → all three pass, (6) gate FAIL: MaxDD=35% → dd_pass=False
- [x] T025 [US3] Update `BacktestEngine.run()` in `src/backtest/backtest_engine.py` to call `compute_metrics(trades, equity_curve, initial_balance)` after all bars processed, set `result.metrics`, write report JSON to `config['backtest']['output_dir']/report_{date}.json` (include config_snapshot, metrics, gate_results, data_period_start/end), write trade CSV to `output_dir/trades_{date}.csv`
- [x] T026 [US3] Implement `backtest_runner.py` at repo root — load `config.yaml`; create `BacktestEngine(config)`; `result = engine.run()`; print formatted report (see quickstart.md sample output); print `=== QUALITY GATE RESULT: PASS/FAIL ===`; exit code 0 if all gates pass, exit code 1 if any gate fails (for CI integration)

**Checkpoint**: US3 complete — `python backtest_runner.py` produces full performance report with PASS/FAIL gates. All US3 tests pass independently.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Wire public exports, verify coverage, run end-to-end smoke test.

- [x] T027 [P] Update `src/orchestrator/__init__.py` with public exports: `StrategyOrchestrator`, `PipelineContext`, `run_pipeline`, `MT5ConnectionError`
- [x] T028 [P] Update `src/backtest/__init__.py` with public exports: `BacktestEngine`, `BacktestResult`, `PerformanceMetrics`, `SimulatedPosition`, `TradeRecord`, `load_ohlcv_csv`, `compute_metrics`, `export_signals`
- [x] T029 [P] Run coverage check: `pytest tests/unit/ -k "pipeline or backtest or performance or bar_monitor or data_loader or position_simulator" --cov=src/orchestrator --cov=src/backtest --cov-report=term-missing` — confirm ≥ 80% for all `src/orchestrator/` and `src/backtest/` files (SC-008). Note: SC-002 (pipeline < 1 second per bar) is a manual verification item — time `run_pipeline()` with `time.time()` on first live bar and confirm < 1.0s; cannot be asserted in unit tests.
- [x] T030 [P] End-to-end smoke test: generate 300-row synthetic XAUUSD H1/D1/H4/M5 CSVs in `tests/fixtures/`; run `python backtest_runner.py --config config.yaml`; confirm (a) exit code 0 or 1 (no crash), (b) `backtest/results/report_{date}.json` written, (c) `backtest/results/signals_{date}.jsonl` written. Note: SC-003 (2-year backtest < 5 minutes) is a manual verification item — time `engine.run()` on full 2-year dataset and confirm < 300 seconds; not measurable in unit tests.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — **BLOCKS Phase 3 and Phase 4**
- **Phase 3 (US1)**: Depends on Phase 2 only — independent of Phase 4
- **Phase 4 (US2)**: Depends on Phase 2 only — independent of Phase 3
- **Phase 5 (US3)**: Depends on Phase 4 (needs BacktestEngine + trades)
- **Phase 6 (Polish)**: Depends on all phases complete

### User Story Dependencies

- **US1 (P1)**: After Phase 2 — fully independent of US2
- **US2 (P1)**: After Phase 2 — fully independent of US1
- **US3 (P2)**: After US2 — shares models.py with US2; depends on BacktestEngine producing TradeRecords

### Within Each Phase

- **Phase 2**: T005 → T006 → T007 (sequential: model before impl before tests)
- **Phase 3 (US1)**: T008 + T009 parallel → T010 → T011 → T012 sequential
- **Phase 4 (US2)**: T013 → T014 parallel with T015+T016 parallel with T017+T018 parallel with T019 → T020 → T021
- **Phase 5 (US3)**: T022 → T023 → T024 (parallel with T025, T026 sequential after T023)
- **Phase 6**: T027–T030 all parallel

### Parallel Opportunities

- T003 (config) and T004 (directories) parallel in Phase 1
- US1 (Phase 3) and US2 (Phase 4) can run in parallel after Phase 2 completes (different files entirely)
- Within US2: T013+T014, T015+T016, T017+T018, T019 are all parallel (different files)
- T027–T030 all parallel in Phase 6

---

## Parallel Execution Example: Phase 4 (US2)

```bash
# After T006 (run_pipeline) is complete, these US2 tasks are all parallel:

# Stream A — Data Loading
T015: load_ohlcv_csv() in src/backtest/data_loader.py
T016: tests/unit/test_data_loader.py

# Stream B — Position Simulation
T017: simulate_bar() in src/backtest/position_simulator.py
T018: tests/unit/test_position_simulator.py

# Stream C — Signal Export (parallel with A and B)
T019: export_signals() in src/backtest/signal_exporter.py

# Stream D — Models (can start even earlier, parallel with Phase 2)
T013: SimulatedPosition + TradeRecord dataclasses in src/backtest/models.py
T014: tests/unit/test_backtest_models.py

# After A, B, C, D complete:
T020: BacktestEngine.run() (depends on all of the above)
T021: tests/integration/test_backtest_full.py
```

---

## Implementation Strategy

### MVP (User Stories 1 + 2 — both P1)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (run_pipeline working and tested)
3. Run US1 and US2 in parallel:
   - US1: bar_monitor → strategy_orchestrator → main.py
   - US2: models → data_loader → position_simulator → signal_exporter → backtest_engine
4. **STOP and VALIDATE**: `python main.py` connects to MT5 demo; `python backtest_runner.py` produces signal JSONL

### Full Delivery

1. Setup + Foundational → shared pipeline ready
2. US1 + US2 in parallel → live loop + backtest engine
3. US3 → performance report + PASS/FAIL gates
4. Polish → coverage gate, exports, smoke test

---

## Notes

- T013 (backtest models) can be written during Phase 2 or at start of Phase 4 — no dependency on run_pipeline
- `src/backtest/` has zero MT5 imports — all backtest files are platform-agnostic and testable anywhere
- `src/orchestrator/pipeline.py` has zero MT5 imports — only `bar_monitor.py` and `strategy_orchestrator.py` import MT5
- The shared `ATRService` instance in live mode is pre-created and passed to `StrategyOrchestrator`; in backtest mode, `BacktestEngine` creates its own isolated instance
- Total tasks: **30** (T001–T030)
- Estimated independence: US1 and US2 share zero source files — perfect for parallel implementation
