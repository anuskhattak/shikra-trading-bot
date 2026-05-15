# Feature Specification: SMC Signal Detection Engine

**Feature Branch**: `002-smc-engine`
**Created**: 2026-05-12
**Status**: Draft
**Asset**: XAUUSD only
**Depends On**: 001-mt5-broker (market data feed)

---

## Overview

The SMC (Smart Money Concepts) Engine is the analytical core of the Shikra system. It processes XAUUSD OHLCV candle data and detects five institutional price patterns — BOS, CHoCH, FVG, Order Block, and Liquidity Sweep — then combines them into a single scored entry signal. Every signal includes a confidence score and a human-readable reason so that all trading decisions are auditable.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Trend Direction Confirmed via BOS / CHoCH (Priority: P1)

The system analyses the H1 chart and determines whether the market is in a bullish trend (Breaking Structure upward = BOS), a bearish trend (Breaking Structure downward = BOS), or reversing direction (Change of Character = CHoCH). This bias informs every subsequent entry decision.

**Why this priority**: Without knowing trend direction, every other signal is meaningless. BOS/CHoCH is the first filter — no entry can be generated without it.

**Independent Test**: Feed a synthetic candle sequence with a clear swing-high break → system must return `BOS_BULLISH`. Feed a sequence where price breaks the most recent swing low after a bullish move → system must return `CHoCH_BEARISH`.

**Acceptance Scenarios**:

1. **Given** 50+ H1 candles with price making higher highs and higher lows, **When** price closes above the most recent swing high, **Then** engine returns `signal_type = BOS_BULLISH` with the broken level recorded.
2. **Given** an established bullish trend, **When** price closes below the most recent swing low (violating structure), **Then** engine returns `signal_type = CHoCH_BEARISH` indicating reversal.
3. **Given** a ranging market with no clear structure break, **When** engine is called, **Then** engine returns `signal_type = NONE` and no entry signal is produced.

---

### User Story 2 — Fair Value Gap (FVG) Identified as Entry Zone (Priority: P2)

After a BOS is confirmed, the engine locates Fair Value Gaps — price imbalances created when institutional orders move the market so fast that a gap forms between candle wicks. These gaps act as high-probability entry zones when price returns to them.

**Why this priority**: FVG is the primary entry trigger in the SMC framework. Without it, the system has no precise entry zone.

**Independent Test**: Feed a 3-candle sequence where candle 1's high does not overlap with candle 3's low → system detects a bullish FVG and records the zone boundaries (top, bottom, midpoint). Confirm zone is marked as `UNFILLED`.

**Acceptance Scenarios**:

1. **Given** 3 consecutive candles where candle 1 high < candle 3 low, **When** engine scans for FVG, **Then** a bullish FVG zone is recorded with `top = candle 3 low`, `bottom = candle 1 high`, `status = UNFILLED`.
2. **Given** a previously detected FVG zone, **When** price closes inside the zone, **Then** zone status updates to `FILLED` and is no longer used as an entry zone.
3. **Given** multiple FVGs on the chart, **When** engine selects entry zone, **Then** the most recent unfilled FVG in the direction of bias is selected.

---

### User Story 3 — Order Block Identified for Precise Entry (Priority: P3)

An Order Block (OB) is the last opposing candle before a significant structural move — the candle where institutions placed their bulk orders. Price returning to an OB is a high-confluence entry opportunity.

**Why this priority**: OBs provide the most precise entry price level and are used in conjunction with FVGs for highest-confidence setups.

**Independent Test**: Identify the last bearish candle before a bullish BOS → mark it as a Bullish Order Block. Confirm the OB zone boundaries (candle body high and low) are recorded correctly.

**Acceptance Scenarios**:

1. **Given** a bullish BOS, **When** engine searches for the origin of the move, **Then** it identifies the last bearish candle before the BOS as a Bullish Order Block with `top = candle body high`, `bottom = candle body low`.
2. **Given** a detected Order Block, **When** price returns to touch the OB zone, **Then** engine marks the OB as `TESTED` and raises entry readiness flag.
3. **Given** an OB that price has fully closed through (violated), **Then** OB is invalidated and removed from active zones.

---

### User Story 4 — Liquidity Sweep Detected as Reversal Confirmation (Priority: P4)

Before reversing, institutions often sweep liquidity resting above equal highs or below equal lows (stop-loss clusters). A Liquidity Sweep followed by a reversal candle is a high-confidence signal that the move is complete and a reversal is beginning.

**Why this priority**: Liquidity sweeps filter out false signals — a CHoCH after a sweep is far more reliable than a CHoCH alone.

**Independent Test**: Feed candles with two equal highs (within 5 pips) followed by a wick that exceeds both highs and closes back below → system detects a `LIQUIDITY_SWEEP_HIGH` event.

**Acceptance Scenarios**:

1. **Given** two or more candles with highs within 5 pips of each other, **When** a subsequent candle wicks above them and closes below, **Then** engine records `LIQUIDITY_SWEEP_HIGH` with the sweep level and the close price.
2. **Given** a Liquidity Sweep event, **When** the next candle confirms a bearish CHoCH, **Then** combined signal confidence score increases by a defined premium (higher weight).
3. **Given** no equal highs or lows within the look-back window, **When** engine is called, **Then** no sweep is detected and signal confidence is unaffected.

---

### User Story 5 — Scored Entry Signal Generated and Logged (Priority: P1)

The engine combines all detected SMC events into a single `EntrySignal` with a confidence score (0.0–1.0) and a human-readable reason string. Signals below the minimum confidence threshold are discarded. Every signal — accepted or rejected — is logged for auditability.

**Why this priority**: The scored signal is the output that all downstream modules (risk manager, order execution) consume. Without it, no trade can be placed.

**Independent Test**: With BOS + FVG + OB all aligned bullish → confidence ≥ 0.7. With only BOS and no FVG or OB → confidence < minimum threshold → signal discarded with reason logged.

**Acceptance Scenarios**:

1. **Given** BOS, FVG, and OB all aligned in the same direction, **When** engine scores the setup, **Then** `EntrySignal.confidence ≥ 0.70` and `direction` is set correctly.
2. **Given** BOS detected but no FVG or OB present, **When** engine scores the setup, **Then** `EntrySignal.confidence < ML_CONFIDENCE_THRESHOLD (0.65)` and signal is discarded with reason `"Insufficient confluence"`.
3. **Given** any signal (accepted or discarded), **When** engine finishes, **Then** signal details are written to `logs/false_signals.json` (for discarded) or passed to risk manager (for accepted).
4. **Given** a Liquidity Sweep preceding the BOS/CHoCH, **When** engine scores, **Then** confidence score receives a sweep bonus and the reason string includes `"+ Liquidity Sweep"`.

---

### Edge Cases

- What happens when fewer than 50 candles are available (insufficient history)? → Engine returns `NONE` signal, logs warning, no entry generated.
- What happens when BOS and CHoCH conflict (fast-moving market)? → Most recent structural event takes precedence; older signal is invalidated.
- What happens when multiple FVGs are stacked in the same zone? → Only the most recent unfilled FVG is used; older ones are archived.
- What happens when an OB and FVG overlap? → OB body is used as `entry_zone` (primary); FVG provides confluence confirmation and confidence bonus. No overlap merging needed.
- What happens when a signal has FVG but no OB? → `entry_zone` falls back to FVG boundaries (top/bottom); confidence score is lower since OB weight (0.20) is absent.
- What happens when the engine is called during a news spike (extreme wick)? → BOS/CHoCH from a single extreme candle is rejected; requires confirmation from the next candle close.

---

## Requirements *(mandatory)*

### Functional Requirements

**BOS / CHoCH Detection**
- **FR-001**: Engine MUST scan H1 OHLCV candles and identify swing highs and swing lows using a fractal rule: a pivot is valid only when it has at least N candles with lower highs (for swing high) or higher lows (for swing low) on both sides. Default N=2, configurable. Look-back window defaults to 20 candles.
- **FR-002**: Engine MUST detect a Break of Structure (BOS) when a candle closes beyond the most recent swing high (bullish BOS) or swing low (bearish BOS).
- **FR-003**: Engine MUST detect a Change of Character (CHoCH) when a candle closes beyond the swing low in an established bullish trend, or beyond the swing high in an established bearish trend.
- **FR-004**: Engine MUST NOT generate a BOS/CHoCH from a single-candle wick — the candle body must close beyond the structure level (candle-close rule).

**FVG Detection**
- **FR-005**: Engine MUST identify a Bullish FVG when candle[N-2].high < candle[N].low (gap between first and third candle with no overlap).
- **FR-006**: Engine MUST identify a Bearish FVG when candle[N-2].low > candle[N].high.
- **FR-007**: Engine MUST determine FVG zone status (`UNFILLED` / `FILLED`) by scanning the candle history passed in — a zone is `FILLED` if any subsequent candle **closes** inside it (candle-close rule; wick entries do not count as fills). No cross-call state is maintained.
- **FR-008**: Engine MUST record FVG zone boundaries: top price, bottom price, and midpoint price.

**Order Block Detection**
- **FR-009**: Engine MUST identify a Bullish Order Block as the last bearish candle (close < open) immediately before a bullish BOS.
- **FR-010**: Engine MUST identify a Bearish Order Block as the last bullish candle (close > open) immediately before a bearish BOS.
- **FR-011**: Engine MUST invalidate an Order Block when price **closes** beyond the OB body in the opposite direction (candle-close rule; wick penetration does not invalidate the OB).
- **FR-012**: Engine MUST record OB zone boundaries using the candle body (open and close), not the full wick.

**Liquidity Sweep Detection**
- **FR-013**: Engine MUST detect equal highs when two or more candle highs are within a configurable pip tolerance (default: 5 pips for XAUUSD).
- **FR-014**: Engine MUST detect a Liquidity Sweep High when a candle wicks above equal highs and closes back below them within the same candle.
- **FR-015**: Engine MUST detect a Liquidity Sweep Low when a candle wicks below equal lows and closes back above them.
- **FR-016**: Engine MUST record the sweep level (the equal high/low price) and the candle close price for each detected sweep.

**Signal Scoring & Output**
- **FR-017**: Engine MUST produce an `EntrySignal` containing: direction (LONG/SHORT), confidence score (0.0–1.0), entry zone (price range), reason string, and timestamp. When an Order Block is present and aligned, `entry_zone` MUST use the OB body (top/bottom) as the entry range. When no OB is present, `entry_zone` falls back to the FVG zone boundaries.
- **FR-018**: Engine MUST calculate confidence score by summing component weights: BOS/CHoCH (required, base), FVG alignment (+weight), OB alignment (+weight), Liquidity Sweep (+bonus).
- **FR-019**: Engine MUST discard any signal with confidence < `ML_CONFIDENCE_THRESHOLD` (default 0.65) and log it to `logs/false_signals.json` with reason `"Below confidence threshold"`.
- **FR-020**: Engine MUST include a human-readable reason string in every `EntrySignal` describing which SMC components were detected (e.g., `"BOS_BULLISH + FVG + OB + Liquidity Sweep"`).
- **FR-021**: Engine MUST operate on H1 candles as primary timeframe and accept a pre-computed `htf_bias: Bias` enum (BULLISH / BEARISH / NEUTRAL) as an optional argument. When `htf_bias` is provided, engine MUST only generate signals that align with the bias direction. No D1/H4 DataFrame is parsed by the engine — bias derivation is the caller's responsibility.
- **FR-022**: Engine MUST return `EntrySignal(direction=NONE)` when no valid setup is found — never `None` or an exception.

**Auditability**
- **FR-023**: Engine MUST log every discarded signal to `logs/false_signals.json` with: timestamp, reason for discard, and confidence score at time of discard.
- **FR-024**: Every accepted `EntrySignal` MUST include the list of SMC components that contributed to its score, for downstream audit trail.

### Key Entities

- **SwingPoint**: A significant price high or low used as structure reference. Attributes: price level, candle index, type (HIGH/LOW), confirmed (bool — true only when N candles on both sides satisfy the fractal rule), fractal_n (int — confirmation window used).
- **FVGZone**: A Fair Value Gap. Attributes: top, bottom, midpoint, direction (BULLISH/BEARISH), status (UNFILLED/FILLED), candle index of formation.
- **OrderBlock**: An institutional order origin zone. Attributes: top, bottom, direction (BULLISH/BEARISH), status (ACTIVE/TESTED/INVALIDATED), candle index.
- **LiquiditySweep**: A stop-hunt event. Attributes: sweep_level, close_price, type (HIGH/LOW), candle index.
- **EntrySignal**: The engine output. Attributes: direction (LONG/SHORT/NONE), confidence (float), entry_zone (top/bottom), reason (str), components (list), timestamp.
- **Bias**: Higher-timeframe directional context enum. Values: BULLISH / BEARISH / NEUTRAL. Passed by caller; engine does not derive it.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: BOS and CHoCH detection produces zero false positives on wick-only moves — candle-body-close rule enforced 100% of the time.
- **SC-002**: FVG zone boundaries are calculated with precision to 2 decimal places matching broker tick data.
- **SC-003**: Order Block identification correctly marks the last opposing candle in ≥ 95% of cases when tested against a hand-labelled dataset of 200 XAUUSD H1 setups.
- **SC-004**: Liquidity Sweep detection identifies sweep events within the same candle they occur — no lag beyond one candle.
- **SC-005**: Engine processes 200 H1 candles and produces a signal decision in under 100 milliseconds.
- **SC-006**: Confidence scoring is deterministic — identical candle input always produces identical confidence score (no randomness).
- **SC-007**: Every discarded signal is present in `logs/false_signals.json` within 1 second of the discard decision.
- **SC-008**: Unit test coverage ≥ 80% for all five detection functions (BOS, CHoCH, FVG, OB, Liquidity Sweep).
- **SC-009**: Backtested against 2+ years of XAUUSD H1 data — Win rate ≥ 50% and Profit Factor ≥ 1.5 for signals with confidence ≥ 0.65.

---

## Non-Functional Requirements

- **NFR-001**: All detection functions must include inline comments explaining the SMC rule being applied (auditability).
- **NFR-002**: Engine must be stateless per call — caller passes the full candle history (DataFrame) on every invocation; engine recomputes all swing points, FVG zones, and OBs from scratch each call. No instance-level state between calls. Enables trivially parallel backtesting.
- **NFR-003**: No live MT5 connection required for signal detection — engine operates purely on pandas DataFrames. MT5 feeds the data; engine is broker-agnostic.

---

## Assumptions

1. H1 candles provided by `MarketData.get_ohlcv(Timeframe.H1)` are OHLCV pandas DataFrames with columns: `time`, `open`, `high`, `low`, `close`, `tick_volume`.
2. Minimum 50 H1 candles required for swing point detection; engine returns `NONE` signal if fewer bars are available.
3. XAUUSD pip value = 0.01 (2 decimal places for price, 5th decimal for pip calculation at broker level — not relevant here since SMC uses price levels, not pips).
4. Confidence score weights are configurable via `config.yaml` with sensible defaults: BOS=0.40, FVG=0.30, OB=0.20, LiquiditySweep=0.10.
5. Equal highs/lows tolerance of 5 pips (= $0.50 for XAUUSD) — configurable.
6. Look-back window for swing detection defaults to 20 candles — configurable.
7. Fractal confirmation window N defaults to 2 candles on each side of the pivot — configurable.

---

## Clarifications

### Session 2026-05-12

- Q: How does the engine receive and return persistent state between calls? → A: Full recompute — engine scans full candle history fresh on every call; no cross-call state maintained. Caller passes the complete OHLCV DataFrame each time.
- Q: How is D1/H4 bias context provided to the engine? → A: Pre-computed enum — caller passes `htf_bias: Bias` (BULLISH/BEARISH/NEUTRAL); engine filters signals to match bias. Engine does not parse higher-timeframe DataFrames.
- Q: How are swing points qualified as significant? → A: Fractal rule — pivot must have N=2 candles with lower highs (or higher lows) on each side. Default N=2, configurable.
- Q: Does FVG fill and OB invalidation trigger on wick touch or candle close? → A: Candle-close rule — zone is FILLED / OB is INVALIDATED only when a candle **closes** inside/beyond the zone. Wick entries do not count. (FR-007, FR-011 updated)
- Q: When BOS + FVG + OB all align, which zone becomes EntrySignal.entry_zone? → A: OB zone (top/bottom of OB body) is primary entry_zone; FVG is fallback when no OB is present. (FR-017 updated)

---

## Out of Scope

- M5 entry refinement (Phase 2).
- ML signal quality filter (Spec 008).
- LSTM H4 bias prediction (Spec 009).
- Supply & Demand zones (may be added as extension to this spec or a separate spec).
- Multi-timeframe confluence scoring beyond H4 bias context.
- Live repainting detection / prevention (candle-close rule in FR-004 is the mitigation).
