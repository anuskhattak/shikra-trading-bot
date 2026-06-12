# Feature Specification: H4 Bias Engine

**Feature Branch**: `007-h4-bias-engine`  
**Created**: 2026-06-12  
**Status**: Draft  
**Input**: H4 directional bias detection using ATR-based swing structure analysis

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - H4 Directional Bias Detection (Priority: P1)

The trading system needs to know the higher-timeframe (H4) market direction before allowing any trade entry on H1. Without knowing whether H4 is Bullish, Bearish, or Ranging, the bot cannot enforce trade-with-trend discipline — the most critical SMC rule.

**Why this priority**: Every H1 trade entry depends on H4 bias alignment. This module is a gating dependency for the entire signal pipeline. Without it, the bot trades blindly against potential institutional flow.

**Independent Test**: Feed 200 H4 bars of known trending/ranging market data → verify the engine outputs BULLISH during up-trends, BEARISH during down-trends, and RANGING during consolidations.

**Acceptance Scenarios**:

1. **Given** H4 price is making higher highs and higher lows consistently, **When** the bias engine analyzes the last N H4 bars, **Then** it returns `BULLISH` with a strength score > 0.6.
2. **Given** H4 price is making lower highs and lower lows consistently, **When** the bias engine analyzes the last N H4 bars, **Then** it returns `BEARISH` with a strength score > 0.6.
3. **Given** H4 price swing highs and lows are not clearly directional, **When** the bias engine runs, **Then** it returns `RANGING` with a strength score < 0.5.

---

### User Story 2 - Trade Blocking on Ranging H4 (Priority: P1)

When the H4 market is ranging (no clear directional structure), the bot must refuse to open new trades. Entering during consolidation leads to whipsaw losses against random price movement.

**Why this priority**: This is a hard safety rule in the SMC strategy. Missing it means the bot will take false signals during low-conviction consolidation phases.

**Independent Test**: Set H4 bias to RANGING, trigger an H1 SMC signal → verify that the signal pipeline logs "BLOCKED: H4 RANGING" and no order is placed.

**Acceptance Scenarios**:

1. **Given** H4 bias is RANGING, **When** a valid H1 BOS/CHoCH signal fires, **Then** the trade entry is blocked and a trace log entry is written with reason `H4_RANGING`.
2. **Given** H4 bias changes from RANGING to BULLISH on a new H4 bar, **When** the next H1 signal fires in the bullish direction, **Then** the trade is allowed through the filter.

---

### User Story 3 - Signal Score Boost on H4 Alignment (Priority: P2)

When the H4 bias aligns with the H1 trade direction, the SMC signal score should receive a boost (+2.0 points) to increase entry confidence. Multi-timeframe confluence is a core SMC entry filter.

**Why this priority**: The alignment boost directly improves signal quality and reduces false entries. It also enables the MTF (multi-timeframe) score multiplier of 1.3x.

**Independent Test**: Generate a BULLISH H1 signal with H4 bias = BULLISH → verify final signal score includes the +2.0 alignment boost and is multiplied by 1.3x.

**Acceptance Scenarios**:

1. **Given** H4 bias is BULLISH and an H1 BUY signal fires, **When** signal scoring runs, **Then** the score includes a +2.0 H4 alignment contribution and the total is multiplied by 1.3x.
2. **Given** H4 bias is BEARISH and an H1 BUY signal fires, **When** signal scoring runs, **Then** no alignment boost is added (counter-trend trade is scored lower).
3. **Given** H4 bias is RANGING and an H1 signal fires, **Then** the trade is blocked before scoring even runs.

---

### User Story 4 - H4 Bias Recalibration on New H4 Bar (Priority: P2)

The H4 bias must recalculate every time a new H4 candle closes. Market structure evolves — a bias that was BULLISH two hours ago may flip to RANGING as new candles form.

**Why this priority**: Stale bias data leads to wrong trade direction. The bias must always reflect the current H4 market structure, not a snapshot from hours ago.

**Independent Test**: Inject a new H4 bar with price making a lower low into a previously BULLISH market → verify the bias updates within the same bar-close event.

**Acceptance Scenarios**:

1. **Given** a new H4 bar closes, **When** the H4 bar event fires, **Then** the bias engine recalculates swing structure using the latest bars.
2. **Given** H4 bias was BULLISH, **When** price breaks the last swing low on the new H4 bar, **Then** bias transitions toward BEARISH or RANGING on that bar's recalculation.

---

### User Story 5 - Bias State Logging for Auditability (Priority: P3)

Every trade entry decision must log the H4 bias state that was active at the time. This is required for backtesting analysis and ML feature generation (Phase 2).

**Why this priority**: Without audit trails, it is impossible to debug wrong trade directions or train the ML signal filter. Logging is a non-negotiable auditability requirement.

**Independent Test**: Run 10 simulated trades → verify each trade log entry contains `h4_bias` field with value BULLISH/BEARISH/RANGING and `h4_bias_strength` float.

**Acceptance Scenarios**:

1. **Given** any trade is entered, **When** the EntrySignal is constructed, **Then** it includes `h4_bias` (string) and `h4_bias_strength` (float 0.0–1.0) fields.
2. **Given** a trade is blocked by RANGING filter, **When** the rejection is logged, **Then** the log entry includes the H4 bias state and timestamp.

---

### Edge Cases

- What happens when H4 OHLCV data has fewer bars than the swing lookback window (cold start)?
- What happens when multiple consecutive H4 bars have equal highs or equal lows (no clear direction)?
- What happens if MT5 returns incomplete H4 data for a single bar (missing OHLCV)?
- What happens when the market transitions from BULLISH to RANGING mid-session — does an in-progress trade get affected?
- How is a tie-breaking ambiguity resolved (one higher high, one lower low in the same lookback)?

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST classify H4 market direction as one of exactly three states: `BULLISH`, `BEARISH`, or `RANGING` on every H4 bar close.
- **FR-002**: The system MUST detect swing highs and swing lows using a configurable lookback window (default: 20 H4 bars) to determine directional structure.
- **FR-003**: The system MUST output a bias strength score between 0.0 and 1.0 alongside the direction label, representing the conviction level of the detected bias.
- **FR-004**: The system MUST classify as BULLISH only when price structure shows a sequence of higher highs and higher lows within the lookback window.
- **FR-005**: The system MUST classify as BEARISH only when price structure shows a sequence of lower highs and lower lows within the lookback window.
- **FR-006**: The system MUST classify as RANGING when price structure does not meet BULLISH or BEARISH criteria.
- **FR-007**: The system MUST block H1 trade entry when H4 bias is RANGING and log the block reason as `H4_RANGING`.
- **FR-008**: The system MUST add a +2.0 signal score contribution when H4 bias direction aligns with the H1 trade direction.
- **FR-009**: The system MUST apply a 1.3x multiplier to the total signal score when H4 and H1 signals are aligned (MTF boost).
- **FR-010**: The system MUST recalculate H4 bias on every new H4 bar close event, using the latest available H4 OHLCV data.
- **FR-011**: The system MUST embed H4 bias state (`h4_bias` and `h4_bias_strength`) into every EntrySignal data structure.
- **FR-012**: The system MUST log every H4 bias state transition (e.g., BULLISH → RANGING) with a timestamp for auditability.
- **FR-013**: The system MUST handle cold-start gracefully when fewer than `swing_lookback` H4 bars are available — returning RANGING with zero strength rather than crashing.
- **FR-014**: The system MUST be designed so that the bias output interface can be replaced or augmented by an LSTM predictor in Phase 3 without changes to downstream modules.

### Key Entities

- **H4BiasResult**: The output produced after each H4 analysis — contains direction (`BULLISH`/`BEARISH`/`RANGING`), strength score (0.0–1.0), detected swing count, and calculation timestamp.
- **SwingPoint**: A detected swing high or swing low on the H4 chart — contains price level, bar index, and direction (HIGH or LOW).
- **BiasStateLog**: Immutable audit record written each time bias state changes — contains previous state, new state, timestamp, and price at transition.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: H4 bias classification matches expected direction (BULLISH/BEARISH/RANGING) on ≥ 80% of labeled test cases from 2 years of XAUUSD H4 data.
- **SC-002**: Trades blocked by RANGING filter show a net improvement in win rate — backtest with RANGING filter enabled must outperform backtest without it by ≥ 5% win rate.
- **SC-003**: Bias recalculation completes within the same H4 bar-close event, with no observable delay to signal pipeline processing.
- **SC-004**: Every EntrySignal produced by the system contains a non-null `h4_bias` and `h4_bias_strength` value — 100% field coverage in trade logs.
- **SC-005**: Cold-start scenario (< 20 H4 bars available) returns RANGING with strength 0.0 without raising an exception — verified by unit test.
- **SC-006**: The H4 bias module interface is replaceable by an LSTM model without modifying the signal scoring or trade execution modules — verified by a stub integration test.

---

## Assumptions

- H4 swing lookback window defaults to 20 bars as defined in `config.py` (`SWING_LOOKBACK = 20`).
- Minimum qualifying swing size is `H1_ATR × 1.5` (per ATR Calibration module output from spec006).
- ATR period is 14 bars as configured (`ATR_PERIOD = 14`).
- The ATR Calibration module (spec006) is already integrated and provides current ATR values at the time this module runs.
- H4 OHLCV data is fetched via the MT5 broker module — this module does not own data fetching.
- The EntrySignal dataclass (defined in the SMC signal pipeline) will be extended to include `h4_bias` and `h4_bias_strength` fields.
- Trade blocking by RANGING is enforced in the main execution pipeline (spec008), not inside this module — this module only outputs the bias state.
- Phase 3 LSTM replacement is out of scope for this spec; the module interface must be designed for replaceability but LSTM implementation is deferred to spec012.
