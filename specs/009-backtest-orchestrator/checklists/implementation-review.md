# Implementation Review Checklist: Backtest Suite & Strategy Orchestrator

**Purpose**: Verify all 30 tasks (T001–T030) are correctly implemented before merging to main
**Created**: 2026-06-12
**Feature**: [spec.md](../spec.md) | [tasks.md](../tasks.md)
**Branch**: `009-backtest-orchestrator`

---

## Phase 1: Setup

- [x] T001 — `src/orchestrator/__init__.py` and `src/backtest/__init__.py` both exist (even if empty)
- [x] T002 — `pandas` present in `requirements.txt`
- [x] T003 — `config.yaml` has `backtest` section (`initial_balance`, `spread_usd`, `data_dir`, `output_dir`, `risk_percent`) AND `orchestrator` section (`max_reconnect_retries`, `reconnect_backoff_base_seconds`)
- [x] T004 — `data/historical/.gitkeep` and `backtest/results/.gitkeep` exist and are tracked by git

---

## Phase 2: Foundational — Shared Pipeline Core

- [x] T005 — `src/orchestrator/models.py` contains **both** `PipelineContext` AND `BarEvent` dataclasses
  - [x] `PipelineContext.mode` accepts `"live"` and `"backtest"` strings
  - [x] `PipelineContext` output fields (`atr_readings`, `entry_signal`, `filter_result`, `risk_calc`) default to `None`/empty — not required at construction
  - [x] `BarEvent.bars_fetched` is `dict[Timeframe, list[OHLCVBar]]` covering all 4 timeframes
- [x] T006 — `src/orchestrator/pipeline.py` exports `run_pipeline(ctx, atr_service, config) -> PipelineContext`
  - [x] Zero `import MetaTrader5` / `import mt5` statements in this file
  - [x] 4 stages run sequentially: ATR refresh → SMC detection → filter evaluation → risk calc
  - [x] Short-circuits at filter BLOCKED: `risk_calc` is `None` when filter blocks
  - [x] Never raises — all exceptions caught and logged internally
- [x] T007 — `tests/unit/test_pipeline.py` has exactly 5 tests covering: full ALLOWED path, filter BLOCKED short-circuit, ATR not ready short-circuit, NONE signal short-circuit, ATR exception graceful recovery

**Checkpoint**: `pytest tests/unit/test_pipeline.py -v` — all 5 pass ✅

---

## Phase 3: User Story 1 — Live Strategy Orchestrator

- [x] T008 — `src/orchestrator/bar_monitor.py` exports `poll_for_new_bar()` and `MT5ConnectionError`
  - [x] Uses `mt5.copy_rates_from_pos()` for detection (2 bars) then full 150-bar fetch on new bar
  - [x] Returns `(True, new_time, bars_dict)` for new bar; `(False, last_bar_time, {})` for no change
  - [x] Raises `MT5ConnectionError` when MT5 returns `None`
  - [x] `last_bar_time=None` on first call → always returns `True` with bars
- [x] T009 — `tests/unit/test_bar_monitor.py` has 4 tests (new bar detected, no new bar, MT5 None → exception, first call with None)
- [x] T010 — `src/orchestrator/strategy_orchestrator.py` — `StrategyOrchestrator` class
  - [x] `_on_new_bar`: condition is `ctx.filter_result.final_result == FilterResult.ALLOWED` (not string comparison)
  - [x] `ctx.now_utc` is set to `new_bar_time` (bar close timestamp) — not `datetime.utcnow()`
  - [x] `current_price = mt5.symbol_info_tick("XAUUSD").last` before `manage_open_positions()`
  - [x] Daily drawdown NOT duplicated — delegated entirely to `ExecutionEngine.run_preflight()`
  - [x] Reconnection uses exponential backoff: `backoff_base ** attempt` seconds, up to `max_reconnect_retries`
  - [x] `_shutdown()` calls `broker.disconnect()` and logs session summary
- [x] T011 — `tests/integration/test_orchestrator_mocked.py` has exactly **5** tests including MT5ConnectionError retry test (FR-008, SC-007)
- [x] T012 — `main.py` at repo root: loads `config.yaml`, instantiates all 5 components, calls `orchestrator.run()`; handles `KeyboardInterrupt` cleanly

**Checkpoint**: `pytest tests/unit/test_bar_monitor.py tests/integration/test_orchestrator_mocked.py -v` — all 9 pass ✅

---

## Phase 4: User Story 2 — Backtest Engine

- [x] T013 — `src/backtest/models.py` contains `SimulatedPosition` and `TradeRecord` (from initial pass; extended in T022)
  - [x] `SimulatedPosition.is_tp1_hit` defaults to `False`; `is_closed` defaults to `False`
  - [x] `TradeRecord` includes `entry_signal_type: str` and `entry_confidence: float`
- [x] T014 — `tests/unit/test_backtest_models.py` has 6 tests including Direction enum consistency check with `src/engine/models.py`
- [x] T015 — `src/backtest/data_loader.py` exports `load_ohlcv_csv(data_dir, timeframe, symbol="XAUUSD") -> list[OHLCVBar]`
  - [x] Reads `{data_dir}/{symbol}_{timeframe.name}.csv`; case-insensitive column matching
  - [x] Parses `datetime` from separate `date` and `time` columns
  - [x] Returns sorted oldest-first
  - [x] Raises `FileNotFoundError` on missing file; `ValueError` on missing required columns
- [x] T016 — `tests/unit/test_data_loader.py` has 5 tests (valid CSV, missing file, missing column, field mapping, extra columns ignored)
- [x] T017 — `src/backtest/position_simulator.py` exports `simulate_bar(position, bar) -> tuple[SimulatedPosition, Optional[TradeRecord]]`
  - [x] TP1 logic: halves `lot_size`, sets `sl_price = entry_price`, sets `is_tp1_hit = True`, returns `None` (position still open)
  - [x] **Conservative rule**: if both SL and TP2 triggered on same bar → SL wins (loss recorded)
  - [x] P&L uses correct `direction_sign`: LONG = +1, SHORT = -1
- [x] T018 — `tests/unit/test_position_simulator.py` has exactly **8** tests including same-bar SL+TP2 = SL wins (D-004)
- [x] T019 — `src/backtest/signal_exporter.py` exports `export_signals(contexts, output_path) -> None`
  - [x] Output format is JSONL (one JSON object per line, not a JSON array)
  - [x] All 13 required fields present per row: `timestamp`, `signal_type`, `confidence`, `filter_result`, `filter_reason`, `direction`, `entry_price`, `sl_price`, `atr_h1_current`, `atr_h1_reference`, `volatility_ratio`, `volatility_regime`, `trade_placed`
- [x] T020 — `src/backtest/backtest_engine.py` — `BacktestEngine` class
  - [x] First 35 H1 bars consumed as warm-up (ATRService.refresh called but no trades opened)
  - [x] `mode="backtest"` set in PipelineContext; `news_events=[]` (FR-011 news filter disabled)
  - [x] Uses fixed `spread_usd = config['backtest']['spread_usd']` (FR-011)
  - [x] `run()` calls `export_signals()` after all bars processed
  - [x] Zero `import MetaTrader5` / `import mt5` in entire `src/backtest/` directory
- [x] T021 — `tests/integration/test_backtest_full.py` has 3 tests: full run completes, JSONL written, determinism (run twice → identical P&L list)

**Checkpoint**: `pytest tests/unit/test_data_loader.py tests/unit/test_position_simulator.py tests/integration/test_backtest_full.py -v` — all 16 pass ✅

---

## Phase 5: User Story 3 — Performance Report

- [x] T022 — `src/backtest/models.py` extended with `PerformanceMetrics` and `BacktestResult`
  - [x] `PerformanceMetrics.gate_results: dict[str, bool]` with keys `"win_rate_pass"`, `"pf_pass"`, `"dd_pass"`
  - [x] `BacktestResult.metrics: Optional[PerformanceMetrics]` (None until T025 wires it)
- [x] T023 — `src/backtest/performance.py` exports `compute_metrics(trades, equity_curve, initial_balance, bar_dates) -> PerformanceMetrics`
  - [x] `profit_factor = float('inf')` when no losing trades; `0.0` when no winning trades
  - [x] Sharpe: groups equity by **calendar day** using `bar_dates` parallel list; uses last H1 bar equity per day; annualizes by `sqrt(252)`; returns `0.0` if std == 0 or < 2 trading days
  - [x] Max drawdown iterates full `equity_curve` tracking running peak (not just trade P&L list)
  - [x] Gate thresholds: win_rate ≥ 50.0, profit_factor ≥ 1.5, max_drawdown_pct < 30.0
- [x] T024 — `tests/unit/test_performance.py` has 6 tests including hand-calculated 10-trade scenario within ±0.1%
- [x] T025 — `BacktestEngine.run()` updated: calls `compute_metrics()` after all bars, writes `report_{date}.json` and `trades_{date}.csv` to `config['backtest']['output_dir']`; `BacktestResult.metrics` populated
- [x] T026 — `backtest_runner.py` at repo root
  - [x] Prints formatted report matching `quickstart.md` sample output format
  - [x] Prints `=== QUALITY GATE RESULT: PASS ===` or `=== QUALITY GATE RESULT: FAIL ===`
  - [x] Exit code `0` if all 3 gates pass; exit code `1` if any gate fails (CI-compatible)

**Checkpoint**: `pytest tests/unit/test_performance.py -v` — all 6 pass ✅; `python backtest_runner.py` exits 0 or 1 without crash ✅

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T027 — `src/orchestrator/__init__.py` exports: `StrategyOrchestrator`, `PipelineContext`, `run_pipeline`, `MT5ConnectionError`
- [x] T028 — `src/backtest/__init__.py` exports: `BacktestEngine`, `BacktestResult`, `PerformanceMetrics`, `SimulatedPosition`, `TradeRecord`, `load_ohlcv_csv`, `compute_metrics`, `export_signals`
- [x] T029 — Coverage check passes: `pytest tests/unit/ tests/integration/ --cov=src/orchestrator --cov=src/backtest --cov-report=term-missing` shows ≥ 80% for all files (lowest: pipeline.py at 83%, strategy_orchestrator.py at 89%) (SC-008)
- [x] T030 — Smoke test: 300-row synthetic CSVs in `tests/fixtures/` and `data/historical/`; `python backtest_runner.py` exits 1 (win_rate gate fails on no-trade synthetic data — no crash); `backtest/results/report_*.json`, `signals_*.jsonl`, `trades_*.csv` written

---

## Contract Invariants (Cross-Task Verification)

- [x] `src/orchestrator/pipeline.py` — zero MT5 imports (verified by `grep -r "MetaTrader5\|import mt5" src/orchestrator/pipeline.py`)
- [x] `src/backtest/` — zero MT5 imports anywhere in directory
- [x] `PipelineContext.mode` is passed through to `run_pipeline()` and accessible for filter overrides (news filter checks `ctx.mode == "backtest"`)
- [x] `BarEvent.bars_fetched` dict covers all 4 timeframes — orchestrator passes it directly without re-fetching
- [x] `TradeRecord.direction` values match `src/engine/models.py` `Direction` enum (no string literals)
- [x] Signal export JSONL is valid: each line parseable with `json.loads()`; all 13 fields present

---

## Functional Requirements Coverage

| FR | Verified By | Status |
|----|-------------|--------|
| FR-001 (broker connect + 100-bar load) | T010 `_startup()`, T011 test 1 | - [x] |
| FR-002 (H1 bar close polling + full pipeline) | T008, T010 `run()`, T011 test 2 | - [x] |
| FR-003 (orchestrator passes bars to ATRService) | T006 stage 1, T010 `_on_new_bar` | - [x] |
| FR-004 (kill switch check before entry) | T010 `_on_new_bar`, T011 test 4 | - [x] |
| FR-005 (daily drawdown via preflight) | T010 comment confirming delegation, T011 test 2 | - [x] |
| FR-006 (log every pipeline decision) | T010 logging in `_on_new_bar` | - [x] |
| FR-007 (clean shutdown + session summary) | T010 `_shutdown()`, T012 KeyboardInterrupt | - [x] |
| FR-008 (MT5 reconnection with retries) | T010 `run()` reconnect loop, T011 test 5 | - [x] |
| FR-009 (backtest loads CSV without MT5) | T015 `load_ohlcv_csv()`, T016 tests | - [x] |
| FR-010 (same signal/filter/risk logic) | T006 `run_pipeline()` shared by T020 | - [x] |
| FR-011 (news disabled, fixed spread in backtest) | T020 `BacktestEngine.run()` PipelineContext | - [x] |
| FR-012 (SL/TP simulation) | T017 `simulate_bar()`, T018 tests | - [x] |
| FR-013 (metrics: WR, PF, Sharpe, MaxDD) | T023 `compute_metrics()`, T024 tests | - [x] |
| FR-014 (signal export JSONL) | T019 `export_signals()`, T030 smoke test | - [x] |
| FR-015 (deterministic backtest) | T021 test 3 | - [x] |
| FR-016 (config.yaml for all backtest values) | T003 config, T020 no hardcoded values | - [x] |
| FR-017 (shared pipeline, no duplication) | T006 single `run_pipeline()` function | - [x] |
| FR-018 (≥ 80% test coverage) | T029 coverage check | - [x] |

---

## Success Criteria Verification

| SC | Verification Method | Status |
|----|---------------------|--------|
| SC-001 (orchestrator ready < 30 sec) | Manual: time `python main.py` startup on MT5 demo | - [ ] |
| SC-002 (pipeline < 1 sec per bar) | **Manual**: `time.time()` around `run_pipeline()` on first live bar | - [ ] |
| SC-003 (2-year backtest < 5 min) | **Manual**: time `engine.run()` on full 2-year dataset | - [ ] |
| SC-004 (metrics within ±1% of hand-calc) | T024 test 1 (±0.1%) | - [x] |
| SC-005 (100% of bars in signal export) | T021 test 2; verify `len(signals) == total_bars_evaluated` | - [x] |
| SC-006 (deterministic runs) | T021 test 3 | - [x] |
| SC-007 (reconnect resumes < 60 sec) | T011 test 5; manual reconnect timing if needed | - [x] |
| SC-008 (≥ 80% unit test coverage) | T029 coverage report | - [x] |
| SC-009 (PASS/FAIL gates in report) | T026 `backtest_runner.py` output | - [x] |

> **SC-002 and SC-003 are manual verification items** — cannot be asserted in unit tests; must be confirmed on real hardware with real data before merge approval.

---

## Final Sign-Off

- [x] All 30 tasks marked `[x]` in `tasks.md`
- [x] `pytest tests/unit/ tests/integration/ -v` — 485 pass; 1 pre-existing live-MT5 failure (terminal offline, not a code bug)
- [x] Coverage ≥ 80% confirmed for `src/orchestrator/` and `src/backtest/` (lowest: pipeline.py 83%)
- [x] `python backtest_runner.py` produces `report_*.json`, `signals_*.jsonl`, `trades_*.csv` without crash
- [ ] `python main.py` starts and logs "ready" on MT5 demo (SC-001 manual check — requires live terminal)
- [ ] SC-002 and SC-003 manually timed and confirmed (manual — requires live terminal + 2-year dataset)
- [x] No hardcoded values (secrets, prices, account numbers) in any new file (verified by grep)
- [x] All new functions have type hints and docstrings (verified by AST scan — all present)
- [ ] Branch `009-backtest-orchestrator` pushed and PR opened against `master`
