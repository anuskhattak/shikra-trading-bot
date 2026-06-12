# Feature Specification: Backtest Suite & Strategy Orchestrator

**Feature Branch**: `009-backtest-orchestrator`  
**Created**: 2026-06-12  
**Status**: Draft  
**Input**: User description: "spec009 — Backtest Suite + Strategy Orchestrator: A unified feature that (1) implements the main Strategy Orchestrator class tying all 6 existing modules together (broker/MT5 → ATR calibration → SMC signal engine → pre-trade filters → risk management → execution engine) into a single trading loop, and (2) implements a Backtest Engine that runs the same orchestrator logic over historical OHLCV data to produce performance metrics (Win%, Profit Factor, Sharpe Ratio, Max Drawdown). The orchestrator is the missing main.py entry point for XAUUSD Gold trading using Smart Money Concepts strategy on MetaTrader 5."

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Live Strategy Orchestrator (Priority: P1)

The Shikra trading bot needs a single entry point that coordinates all six existing modules into a coherent live trading loop. Currently, each module works in isolation — there is no code that ties broker connection → ATR calibration → SMC signal detection → pre-trade filters → risk calculation → order execution into a sequential, bar-driven pipeline.

The orchestrator starts the bot, connects to MT5, warms up all data caches, and then continuously monitors for new H1 bar closes. On each bar close, it runs the full pipeline and places a trade if all conditions are met — or logs the rejection reason if any filter blocks the signal.

**Why this priority**: Without the orchestrator, the bot cannot trade live at all. All six modules are complete but disconnected — this is the missing glue that makes them a working system.

**Independent Test**: Feed the orchestrator a mocked MT5 connection that emits a sequence of synthetic bar-close events. Verify that each event triggers the correct pipeline calls in the correct order, and that the orchestrator handles both allowed and blocked signals.

**Acceptance Scenarios**:

1. **Given** a valid MT5 demo account, **When** the orchestrator starts, **Then** it connects to the broker, loads at least 100 bars of OHLCV history for all four timeframes, and logs "ready" within 30 seconds.
2. **Given** the orchestrator is running and a new H1 bar closes, **When** SMC signals are detected and all filters pass, **Then** the orchestrator submits an order and logs the entry with entry price, SL, TP, and reason.
3. **Given** the orchestrator is running and the volatility filter blocks a signal, **When** the pipeline evaluates the signal, **Then** no order is placed and the rejection reason is logged with the signal ID.
4. **Given** the daily drawdown limit is reached, **When** the orchestrator detects this condition, **Then** it stops placing new orders for the rest of the day and logs the circuit-breaker event.
5. **Given** the kill switch is activated (externally written), **When** the orchestrator next checks, **Then** it stops all new order placement immediately while continuing to manage open positions.

---

### User Story 2 — Backtest Engine (Priority: P1)

To validate the strategy before live trading — and to generate the signal history required for ML training (spec007) — the system needs a backtest engine that replays historical OHLCV data through the same pipeline logic used for live trading.

The backtest engine processes historical bars chronologically, simulates position opens and closes (SL/TP hit detection), and records every trade decision. Its output is both a performance report and a raw signal export suitable for ML feature engineering.

**Why this priority**: The quality guarantee in CLAUDE.md requires backtesting with ≥ 2 years of data, Win Rate ≥ 50%, Profit Factor ≥ 1.5, and Max Drawdown < 30% before any live trading. Without this, the bot cannot be approved for deployment. Additionally, spec007 (ML Signal Filter) cannot be built without signal history data.

**Independent Test**: Run the backtest engine on a known dataset (e.g., 6 months of synthetic XAUUSD H1 data with known trade outcomes). Verify the trade log matches hand-calculated results and performance metrics are within ±1% of manually computed values.

**Acceptance Scenarios**:

1. **Given** a CSV file of historical OHLCV bars, **When** the backtest engine processes it, **Then** it produces a trade log with every entry and exit, including direction, prices, P&L, and the SMC signal reason.
2. **Given** a completed backtest run, **When** performance metrics are requested, **Then** the system returns Win Rate, Profit Factor, Sharpe Ratio (annualised daily returns), and Max Drawdown (peak-to-trough equity).
3. **Given** the same historical dataset run twice, **When** results are compared, **Then** both runs produce identical trade logs and metrics (deterministic execution).
4. **Given** a simulated position is open and a future bar's low touches the stop-loss price, **When** the backtest engine processes that bar, **Then** the position is closed at the stop-loss price and the loss is recorded.
5. **Given** the backtest completes, **When** the signal export file is inspected, **Then** it contains one row per bar evaluated with: timestamp, SMC signal type, confidence score, filter result, direction — suitable for ML training.

---

### User Story 3 — Backtest Performance Report (Priority: P2)

The backtest engine must produce a human-readable performance report summarising the strategy's historical effectiveness. This report is required before any live trading is approved, and it serves as the baseline for future strategy improvements.

**Why this priority**: The CLAUDE.md quality gate requires documented backtest results. Without a structured report, the senior architect cannot approve the system for live deployment.

**Independent Test**: Run a backtest on at least 1 year of data and verify the report file is generated with all required metrics populated and within ±1% of independently calculated values.

**Acceptance Scenarios**:

1. **Given** a completed backtest, **When** the report is generated, **Then** it includes total trades, Win Rate (%), Profit Factor, Sharpe Ratio, Max Drawdown (% and USD), average trade duration, and largest single loss.
2. **Given** the backtest report, **When** compared to the strategy's minimum thresholds, **Then** it clearly indicates PASS or FAIL for each gate: Win Rate ≥ 50%, Profit Factor ≥ 1.5, Max Drawdown < 30%.
3. **Given** the backtest report is exported, **When** reviewed, **Then** it is available in both JSON (machine-readable) and a human-readable text summary.

---

### Edge Cases

- What happens when the MT5 connection drops mid-session while the orchestrator is running?
- What happens if a new bar closes while the previous bar's pipeline is still executing?
- What if the historical OHLCV data has gaps (weekend, holiday) causing fewer than 14 valid bars for ATR?
- What if a backtest position is simultaneously at SL and TP on the same bar (gap open)?
- What if no SMC signals are generated for an entire trading session?
- What happens if the backtest dataset is shorter than the ATR warm-up period (35 H1 bars minimum: ATR period=14 + reference_period=20 + 1)?
- What if the daily drawdown is restored by open position gains — can trading resume?

---

## Requirements *(mandatory)*

### Functional Requirements

**Orchestrator:**

- **FR-001**: The orchestrator MUST connect to MT5 on startup, load at least 100 bars of OHLCV history for all four timeframes (M5, H1, H4, D1), and initialise ATRService before processing any bar events.
- **FR-002**: The orchestrator MUST detect new H1 bar closes by polling and trigger the full pipeline: ATR refresh → SMC signal detection → filter evaluation → risk calculation → execution decision.
- **FR-003**: The orchestrator MUST pass pre-fetched OHLCV bars to ATRService.refresh() — it MUST NOT allow ATRService to fetch data directly.
- **FR-004**: The orchestrator MUST check the kill switch state before every new order placement. Kill switch activation MUST stop new entries immediately; open position management MUST continue regardless.
- **FR-005**: The orchestrator MUST enforce the daily drawdown circuit breaker: if the session's realised loss exceeds the configured threshold (e.g., 5% of opening balance), no new orders are placed for the remainder of that trading day.
- **FR-006**: The orchestrator MUST log every pipeline decision — both accepted trades and rejected signals — with a unique signal ID, timestamp, filter results, and execution outcome.
- **FR-007**: The orchestrator MUST disconnect from MT5 cleanly on shutdown (normal exit or keyboard interrupt) and log the session summary (trades placed, P&L, duration).
- **FR-008**: The orchestrator MUST recover from MT5 disconnection during a session — attempt reconnection up to a configurable number of retries before halting.

**Backtest Engine:**

- **FR-009**: The backtest engine MUST load historical OHLCV data from a CSV file (or MT5 history export) without requiring a live MT5 connection.
- **FR-010**: The backtest engine MUST run the same signal detection, filter evaluation, and risk calculation logic used by the live orchestrator — no separate backtest-specific signal logic.
- **FR-011**: The news filter MUST be disabled in backtest mode (no live news feed available); spread MUST use a fixed configurable value (config: `backtest.spread_usd`).
- **FR-012**: The backtest engine MUST simulate position management: for each open simulated position, check if the current bar's high/low crosses the SL or TP price. SL hit → close at SL price. TP2 hit → close at TP2 price. TP1 hit → close half at TP1 price, set breakeven SL.
- **FR-013**: The backtest engine MUST compute and report: Win Rate (%), Profit Factor (gross profit ÷ gross loss), Sharpe Ratio (annualised, using daily equity returns), Max Drawdown (peak-to-trough equity as % and USD), total trades, average trade duration.
- **FR-014**: The backtest engine MUST export a signal log file containing one row per bar evaluated with: timestamp, SMC signal type, confidence score, filter result (ALLOWED/BLOCKED + reason), direction, and entry price if trade was placed. This file is the primary input for spec007 ML training.
- **FR-015**: The backtest engine MUST be deterministic — the same input data always produces the same trade log, metrics, and signal export.
- **FR-016**: All backtest configuration values (initial balance, spread, risk %, ATR periods, filter thresholds) MUST be loaded from config.yaml under a `backtest` section, with no hardcoded values.

**Shared:**

- **FR-017**: The pipeline core (signal detection → filters → risk → execution decision) MUST be implemented as a shared function or class usable by both the live orchestrator and the backtest engine — no code duplication.
- **FR-018**: Unit test coverage for the pipeline core, orchestrator startup/shutdown, and backtest metrics calculation MUST be ≥ 80%.

### Key Entities

- **StrategyOrchestrator**: Main controller for live trading. Owns the ATRService instance, manages the bar-polling loop, coordinates all six modules, and handles MT5 connection lifecycle.
- **BacktestEngine**: Offline historical simulator. Loads OHLCV data, replays bars chronologically, simulates position open/close, and generates the performance report and signal export.
- **PipelineContext**: Shared data container for one bar's evaluation — holds the current bar, ATR readings, detected SMC signals, filter result, risk calculation, and execution outcome. Passed through the pipeline in both live and backtest modes.
- **SimulatedPosition**: A hypothetical open trade during backtesting — tracks entry price, direction, SL, TP1, TP2, lot size, and accumulated P&L.
- **BacktestResult**: The complete output of a backtest run — trade log, equity curve (one entry per bar), and all performance metrics.
- **TradeRecord**: One completed round-trip (entry + exit) — includes entry price, exit price, direction, P&L USD, entry reason (SMC signal components), exit reason (SL/TP/manual), bar count held.
- **BarEvent**: A new closed bar on a specific timeframe — the trigger that initiates ATR refresh and pipeline execution. Contains the timeframe, bar OHLCV data, and timestamp.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The live orchestrator starts, connects to MT5, loads all historical data, and logs "ready" within 30 seconds of launch.
- **SC-002**: The full pipeline (ATR refresh → signal detection → filters → risk → execution decision) completes within 1 second per H1 bar close under normal conditions.
- **SC-003**: A backtest over 2 years of H1 XAUUSD data (approximately 17,000 bars) completes within 5 minutes on standard hardware (quad-core CPU, 8GB RAM).
- **SC-004**: Backtest performance metrics (Win Rate, Profit Factor, Max Drawdown) match hand-calculated values from the same trade log within ±1%.
- **SC-005**: The signal export file contains all required ML training fields for 100% of bars evaluated during backtesting.
- **SC-006**: Backtest execution is fully deterministic — running the same dataset twice produces identical trade logs, metrics, and signal exports.
- **SC-007**: The orchestrator recovers from an MT5 disconnection and resumes processing within 60 seconds, without losing track of open positions.
- **SC-008**: Unit test coverage for pipeline core, orchestrator logic, and backtest metrics is ≥ 80%.
- **SC-009**: The backtest report clearly shows PASS/FAIL against each quality gate: Win Rate ≥ 50%, Profit Factor ≥ 1.5, Max Drawdown < 30%.

---

## Assumptions

- H1 is the primary signal timeframe; D1 ATR is used for position sizing; M5 and H4 ATR are computed and cached but have no named consumer in this spec (spec007/008 will consume them).
- Historical OHLCV data is available from MT5 or CSV export for at least 2 years — minimum data requirement for backtest quality gate.
- Bar close detection in live mode uses periodic polling (every 10 seconds) to detect when a new H1 bar has formed — not MT5 event callbacks (which are not reliably available in the Python API).
- Sharpe Ratio is computed using daily equity returns (sum of closed trade P&L per calendar day) with risk-free rate = 0.
- In backtest mode, partial TP1 close uses exactly 50% of original lot size (matching live execution spec005 `tp1_close_ratio: 0.5`).
- Daily drawdown circuit breaker resets at the start of each new calendar day (UTC midnight), not per-session.
- The orchestrator processes only XAUUSD — no multi-symbol support in this spec.
- Backtest slippage is not simulated (orders fill at exactly SL/TP prices) — this is conservative and acceptable for Phase 1.
- News filter is disabled in backtest mode. All other filters (session, spread, volatility) are applied using configurable backtest parameters.
- The orchestrator does not manage position sizing recovery across sessions — in-recovery state (spec003) is reset on every restart.

---

## Out of Scope

- Real-time tick-level order simulation (fills at bid/ask mid, not exact price).
- Multi-asset or multi-symbol trading.
- Walk-forward optimisation or parameter sweeps.
- Live news feed integration for backtesting.
- Telegram/email alert integration (spec010).
- ML-based signal filtering (spec007) — the signal export from this spec feeds spec007; the ML model itself is out of scope here.
- LSTM H4 bias prediction (spec008).
- Persistent position state across restarts (open positions are re-read from MT5 on startup but recovery logic uses live position data, not a local state file).
