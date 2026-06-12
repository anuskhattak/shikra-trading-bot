# Feature Specification: ATR Calibration Module

**Feature Branch**: `006-atr-calibration`
**Created**: 2026-05-22
**Status**: Draft
**Input**: User description: "ATR Calibration Module (spec006) — Multi-timeframe ATR calculation (M5, H1, H4, D1) from OHLCV data, reference ATR computation for volatility filter, ATR-adaptive SL/TP multipliers that adjust based on volatility regime, and ATR caching with periodic refresh mechanism for XAUUSD Gold trading bot"

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - ATR Values Available for Signal Pipeline (Priority: P1)

The trading bot's signal pipeline requires accurate ATR values for multiple timeframes before it can assess volatility, size positions, and set stop-loss levels. When a new bar closes on any timeframe, the bot must immediately have fresh ATR values available without recalculating from scratch on every tick.

**Why this priority**: Without ATR values, the lot calculator cannot determine stop-loss distances and the volatility filter cannot classify the regime. This blocks all trade execution.

**Independent Test**: Feed OHLCV data for each timeframe and verify ATR values are computed correctly — this delivers a standalone ATR computation service usable by any module.

**Acceptance Scenarios**:

1. **Given** 14+ bars of OHLCV data for any timeframe, **When** the system requests the ATR, **Then** it returns a positive, non-zero ATR value within ±0.1% of a hand-calculated reference value.
2. **Given** the system has computed ATR for a timeframe, **When** the same ATR is requested again before a new bar closes, **Then** the cached value is returned without recomputation.
3. **Given** a new bar closes on a timeframe, **When** ATR is requested for that timeframe, **Then** the system returns an updated value reflecting the newly closed bar.

---

### User Story 2 - Reference ATR for Volatility Regime Classification (Priority: P1)

The volatility filter (spec004) requires both a current ATR and a reference ATR to compute a ratio and classify the market as LOW, NORMAL, or EXTREME volatility. This module must compute and supply both values so the filter can operate correctly.

**Why this priority**: Without reference ATR, the volatility filter cannot classify regimes, and trades during extreme or low-volatility conditions cannot be blocked.

**Independent Test**: Verify that the reference ATR equals the rolling average of the last 20 ATR values and that the ratio is 1.0 when current equals reference — fully testable in isolation.

**Acceptance Scenarios**:

1. **Given** at least 20 periods of ATR history, **When** reference ATR is requested, **Then** it equals the rolling average of the last 20 ATR values (deterministic, same input → same output).
2. **Given** current ATR equals reference ATR, **When** the volatility ratio is computed, **Then** it equals 1.0 (NORMAL regime).
3. **Given** current ATR is 2× the reference ATR, **When** the ratio is computed, **Then** it equals 2.0 and triggers EXTREME regime classification in the volatility filter.

---

### User Story 3 - Adaptive SL/TP Multipliers by Volatility Regime (Priority: P2)

Stop-loss and take-profit distances must adapt to market volatility. In low-volatility conditions, tighter stops are appropriate; in high-volatility conditions, wider stops prevent premature stop-outs. The SL/TP multipliers used during position sizing must be dynamically selected based on the current volatility regime.

**Why this priority**: Fixed multipliers cause excessive stop-outs in volatile conditions or unnecessarily wide stops in quiet markets — both hurt the bot's risk-adjusted profitability.

**Independent Test**: For each of the three regimes (LOW, NORMAL, EXTREME), verify the system returns the configured multiplier value — testable without any live data.

**Acceptance Scenarios**:

1. **Given** a NORMAL volatility regime, **When** the adaptive SL multiplier is requested, **Then** the default SL multiplier (1.5×) is returned.
2. **Given** an EXTREME volatility regime, **When** the adaptive SL multiplier is requested, **Then** the expanded SL multiplier (2.0×) is returned to widen the stop.
3. **Given** a LOW volatility regime, **When** the adaptive SL multiplier is requested, **Then** the tighter SL multiplier (1.0×) is returned.
4. **Given** any regime, **When** adaptive TP multiplier is requested, **Then** the corresponding TP multiplier (LOW: 2.0×, NORMAL: 3.0×, EXTREME: 4.0×) is returned.

---

### User Story 4 - ATR Cache with Bar-Close Refresh (Priority: P2)

ATR values must not be recomputed on every price tick. Instead, values are cached per timeframe and refreshed only when a new bar closes on that timeframe. On system startup (empty cache), the system automatically fetches historical OHLCV data and populates the cache before serving any requests.

**Why this priority**: Without caching, a high-tick-rate environment causes unnecessary computation and potential latency in the execution pipeline on every single tick.

**Independent Test**: Verify that repeated requests within the same bar return the identical cached value, and a bar-close event triggers cache invalidation and recomputation.

**Acceptance Scenarios**:

1. **Given** ATR was computed at bar open, **When** multiple tick-level requests arrive without a new bar closing, **Then** the same cached ATR value is returned each time.
2. **Given** a new H1 bar closes, **When** ATR is next requested for H1, **Then** the cache is invalidated and a fresh ATR is computed from the latest OHLCV data.
3. **Given** the cache is empty at system startup, **When** ATR is first requested for any timeframe, **Then** the system fetches sufficient OHLCV history and computes ATR before returning a value.
4. **Given** an ATR refresh fails (e.g., data source temporarily unavailable), **When** ATR is requested, **Then** the last valid cached value is returned and the failure is logged.

---

### Edge Cases

- What happens when fewer than 14 bars of OHLCV data are available (new session or market just opened)?
- How does the system handle gaps in OHLCV data (missing bars due to weekend or public holiday)?
- What if OHLCV data contains invalid bars (High < Low, or Close ≤ 0)?
- What if the computed ATR is abnormally large (data spike during major news event)?
- What happens when the MT5 data source drops mid-session during a cache refresh attempt?
- What if all 20 reference ATR periods have the same value (perfectly flat market)?

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST compute True Range (TR) for each OHLCV bar as: `TR = max(High − Low, |High − PrevClose|, |Low − PrevClose|)`.
- **FR-002**: The system MUST compute ATR as the simple average of the True Range over a configurable lookback period (default: 14 bars).
- **FR-003**: The system MUST compute ATR independently for four timeframes: M5, H1, H4, and D1.
- **FR-004**: The system MUST compute a reference ATR as the rolling average of the last N ATR values (default: N = 20 periods), serving as the stable baseline for volatility ratio calculation.
- **FR-005**: The system MUST expose current H1 ATR and H1 reference ATR to the volatility filter module (spec004) as named outputs.
- **FR-006**: The system MUST expose D1 ATR to the lot size calculator (spec003) as a named output for stop-loss distance calculation.
- **FR-007**: The system MUST return an adaptive SL multiplier based on current volatility regime: LOW → 1.0×, NORMAL → 1.5×, EXTREME → 2.0× (all values configurable).
- **FR-008**: The system MUST return an adaptive TP multiplier per regime: LOW → 2.0×, NORMAL → 3.0×, EXTREME → 4.0× (all values configurable).
- **FR-009**: The system MUST cache ATR values per timeframe and invalidate the cache only when a new bar closes on that timeframe.
- **FR-010**: On cache miss (startup or first request), the system MUST ensure sufficient OHLCV history is available (supplied by the orchestrator via the broker module) to fill the ATR lookback window before returning a value. The ATR module does not fetch data directly — it receives pre-fetched bars from its caller.
- **FR-011**: If an ATR refresh attempt fails, the system MUST return the last valid cached value and log the failure with timestamp and timeframe — it MUST NOT return zero or raise an unhandled error.
- **FR-012**: The system MUST reject OHLCV bars where High < Low or Close ≤ 0 as invalid, skip them in ATR computation, and log a warning per rejected bar.
- **FR-013**: All configuration values owned by this module (ATR period, reference period, SL/TP multipliers per regime) MUST be externally configurable without code changes. Volatility regime thresholds (low_atr_ratio, extreme_atr_ratio) remain in the `filters.volatility` config section (spec004) and are not duplicated here.

### Key Entities

- **ATRReading**: A single computed ATR result — includes timeframe, current ATR value, reference ATR value, volatility ratio (current ÷ reference), bar_count (number of valid bars used), and timestamp of computation.
- **VolatilityRegime**: Enumeration of LOW / NORMAL / EXTREME, derived from the ATR ratio against configurable low and extreme thresholds.
- **AdaptiveMultipliers**: A pair of SL multiplier and TP multiplier values, selected based on the current VolatilityRegime.
- **ATRCache**: Per-timeframe store of the most recent ATRReading, with a freshness flag indicating whether the value reflects the latest closed bar.
- **OHLCVBar**: Source input data — Open, High, Low, Close, Volume, and Timestamp for a single bar on a given timeframe.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: ATR values computed from OHLCV data match a hand-calculated reference within ±0.1% for all four timeframes (M5, H1, H4, D1).
- **SC-002**: 100% of intra-bar ATR requests on any timeframe are served from cache — no recomputation occurs between bar closes.
- **SC-003**: ATR cache refresh completes and fresh values are available within 1 second of a new bar closing under normal data source conditions.
- **SC-004**: The correct adaptive multiplier is returned for all three volatility regimes in 100% of unit test cases.
- **SC-005**: When fewer than 14 bars of valid OHLCV data are available, the system returns an explicit unavailable state rather than a calculated but unreliable value.
- **SC-006**: Unit test coverage for ATR calculation, caching, and multiplier selection logic is ≥ 80%.
- **SC-007**: Reference ATR computation is deterministic — the same historical ATR series always produces the same reference ATR value with no randomness or side effects.

---

## Assumptions

- ATR lookback period defaults to 14 bars (Wilder's standard; widely accepted in XAUUSD trading).
- Reference ATR uses a 20-period rolling window of ATR values — long enough to represent approximately one trading week of H1 bars.
- Volatility regime thresholds: LOW if ratio < 0.7, EXTREME if ratio ≥ 2.0, NORMAL otherwise — aligned with existing `volatility_filter.py` in spec004.
- H1 ATR is the primary timeframe for volatility regime classification; D1 ATR is the primary input for SL distance sizing.
- Adaptive multipliers apply to the SL/TP calculation in spec003 (lot_calculator.py) — the ATR module supplies multipliers, the risk module applies them.
- OHLCV data is sourced from the MT5 broker module (spec001); this module does not own the data connection.
- The ATR cache is in-memory only — it is not persisted to disk and is rebuilt from historical data on every system startup.
- Simple (arithmetic) average is used for ATR, not Wilder's exponential smoothing, to keep computation transparent and testable.
- M5 and H4 ATR are computed and accessible via the generic `get_atr(Timeframe.M5)` / `get_atr(Timeframe.H4)` interface. In Phase 1 (spec006), they have no named downstream consumer; spec007 (h4-bias-engine) and spec008 (bot-orchestrator) will consume them when implemented.
- OHLCV data gaps (missing bars due to weekends or public holidays) are handled implicitly: missing bars simply reduce the valid bar count, and the system falls back to None if valid bars drop below 14 (D-007 applies — no special gap-detection logic is required).
- The ATR module does not call the MT5 broker directly — all OHLCV data is pre-fetched by the orchestrator (spec008) via market_data.py (spec001) and passed into ATRService.refresh().

---

## Out of Scope

- H4 directional bias detection (Bullish/Bearish/Ranging) — covered in spec007 (h4-bias-engine).
- Tick-level ATR or volume-weighted ATR variants.
- ATR forecasting or prediction models.
- Persisting ATR history to disk or database between sessions.
- Any indicator beyond ATR (RSI, Bollinger Bands, etc.).
