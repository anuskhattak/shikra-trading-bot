# Feature Specification: Session & Pre-Trade Filters

**Feature Branch**: `004-session-filters`  
**Created**: 2026-05-19  
**Status**: Draft  
**Input**: User description: "004-session-filters: London/NY/Asian session detection, overlap logic, trade window control, spread filter, news filter, volatility regime pre-filter for XAUUSD Gold trading bot"

---

## Overview

The Session & Pre-Trade Filters module acts as a gatekeeper between signal generation and trade execution. Before any SMC signal (BOS, CHoCH, FVG, OB, LS) can trigger a trade, it must pass through a series of pre-trade filters that validate market conditions. These filters prevent trading during unfavorable windows — such as illiquid Asian sessions, high-spread moments, major news events, or abnormal volatility regimes.

This module does not generate signals; it only approves or rejects them.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Session Window Enforcement (Priority: P1)

The trading system automatically identifies which market session is currently active (Asian, London, New York, or London/NY overlap) and permits or blocks trading accordingly. For XAUUSD, only the London session, NY session, and their overlap window are approved trading periods.

**Why this priority**: Trading Gold during the Asian session yields poor results — low liquidity, tight ranges, and frequent false breakouts. Session gating is the most fundamental pre-trade control.

**Independent Test**: Can be tested standalone by feeding timestamps from different sessions and verifying the system returns correct `ALLOWED` or `BLOCKED` status with reason.

**Acceptance Scenarios**:

1. **Given** the current UTC time is 13:30 (London/NY overlap), **When** a signal arrives, **Then** the filter returns `ALLOWED` with session label `LONDON_NY_OVERLAP`
2. **Given** the current UTC time is 04:00 (Asian session), **When** a signal arrives, **Then** the filter returns `BLOCKED` with reason `ASIAN_SESSION_EXCLUDED`
3. **Given** the current UTC time is 08:30 (London session, pre-overlap), **When** a signal arrives, **Then** the filter returns `ALLOWED` with session label `LONDON`
4. **Given** it is a Saturday or Sunday, **When** any signal arrives, **Then** the filter returns `BLOCKED` with reason `MARKET_CLOSED`

---

### User Story 2 — Spread Filter (Priority: P1)

Before executing any trade, the system checks the current bid-ask spread on XAUUSD. If the spread exceeds a configured threshold (e.g., $0.50 USD), the trade is blocked and logged. Spread is always measured in USD for XAUUSD.

**Why this priority**: Wide spreads directly increase trading costs and reduce profitability. Spread spikes are common during news releases and session transitions — entering during a spike can immediately put a trade in significant loss.

**Independent Test**: Can be tested by feeding simulated spread values (normal, borderline, and spike) and verifying the filter correctly approves or rejects with spread value logged.

**Acceptance Scenarios**:

1. **Given** the current spread is $0.30 (below threshold), **When** a signal arrives, **Then** the filter returns `ALLOWED` with spread value logged
2. **Given** the current spread is $1.20 (above threshold), **When** a signal arrives, **Then** the filter returns `BLOCKED` with reason `SPREAD_TOO_WIDE` and spread value logged
3. **Given** the spread threshold is changed in configuration, **When** the system restarts, **Then** the new threshold is applied without code changes

---

### User Story 3 — News Event Filter (Priority: P2)

The system maintains an awareness of high-impact economic news events (FOMC, NFP, CPI, Gold-specific reports) and blocks trading during a configurable window before and after each event.

**Why this priority**: Gold is extremely sensitive to macroeconomic events. News-driven candles can trigger false SMC signals and produce large adverse moves. Trading around news is a common cause of stop-loss hits.

**Independent Test**: Can be tested by loading a sample economic calendar and verifying the filter correctly identifies blackout periods for given timestamps.

**Acceptance Scenarios**:

1. **Given** a high-impact news event (e.g., US NFP) is scheduled at 12:30 UTC, **When** a signal arrives at 12:05 UTC (within 30-min pre-event window), **Then** the filter returns `BLOCKED` with reason `NEWS_BLACKOUT_PRE_EVENT`
2. **Given** the same NFP event at 12:30 UTC, **When** a signal arrives at 12:45 UTC (within 15-min post-event window), **Then** the filter returns `BLOCKED` with reason `NEWS_BLACKOUT_POST_EVENT`
3. **Given** no high-impact news within the blackout window, **When** a signal arrives, **Then** the news filter returns `ALLOWED`
4. **Given** the economic calendar data is unavailable (API failure), **When** a signal arrives, **Then** the system defaults to `BLOCKED` with reason `NEWS_CALENDAR_UNAVAILABLE` (fail safe)

---

### User Story 4 — Volatility Regime Pre-Filter (Priority: P2)

The system assesses the current volatility regime using recent price range data and classifies it as LOW, NORMAL, or EXTREME. Trading is only permitted in the NORMAL regime; both LOW and EXTREME regimes block trade entry.

**Why this priority**: SMC signals require directional momentum to work. In low volatility (choppy/ranging market), signals produce false breakouts. In extreme volatility (news spike, flash crash), signals are unreliable and risk is uncontrollable.

**Independent Test**: Can be tested independently by providing recent OHLC candle data and verifying the regime classification and filter decision.

**Acceptance Scenarios**:

1. **Given** the recent candle ranges are significantly below the average (low volatility), **When** a signal arrives, **Then** the filter returns `BLOCKED` with reason `VOLATILITY_TOO_LOW`
2. **Given** the recent candle range is 5× or more above the average (spike/extreme), **When** a signal arrives, **Then** the filter returns `BLOCKED` with reason `VOLATILITY_EXTREME`
3. **Given** candle ranges are within normal bounds, **When** a signal arrives, **Then** the volatility filter returns `ALLOWED` with `FilterDecision.metric_value` set to the current ATR ratio (float)
4. **Given** the volatility regime is NORMAL, **When** a signal arrives, **Then** trading is permitted (cooldown enforcement after EXTREME transition is deferred to Spec 006 — ATR Calibration)

---

### Edge Cases

- What happens when the system clock is in a local timezone different from UTC? → All session logic must operate in UTC exclusively.
- What happens if two filters disagree (session says ALLOWED, spread says BLOCKED)? → ANY single BLOCKED result blocks the trade; all filters must pass.
- What happens during Daylight Saving Time transitions (clocks change in US/UK)? → Session boundaries must account for DST shifts in London (BST) and New York (EDT/EST).
- What happens when the broker returns an invalid or zero spread value? → Treat as BLOCKED; log error and alert.
- What happens at the exact boundary of a session window (e.g., exactly 16:00 UTC)? → Use inclusive start, exclusive end: `[07:00, 16:00)` — 16:00 is excluded.
- What happens during major holidays (Christmas, New Year) when liquidity is thin? → System should treat major market holidays as `MARKET_CLOSED`.
- What happens between 21:00–00:00 UTC (after NY close, before Asian open)? → This window is classified as `CLOSED`; no trades permitted.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST identify the current market session (ASIAN, LONDON, NEW_YORK, LONDON_NY_OVERLAP, CLOSED) based on UTC time; the post-NY gap (21:00–00:00 UTC) MUST be classified as CLOSED
- **FR-002**: System MUST block trade signals generated during the Asian session (00:00–07:00 UTC), post-NY gap (21:00–00:00 UTC), weekends (Saturday and Sunday), and major market holidays; major holidays are defined as: New Year's Day (Jan 1), Good Friday, Easter Monday, Christmas Day (Dec 25), and Boxing Day (Dec 26)
- **FR-003**: System MUST allow trading during London session (08:00–17:00 Europe/London local time), New York session (08:00–17:00 America/New_York local time), and their overlap window (when both sessions are simultaneously open); UTC-equivalent times shift seasonally — approximate summer values are 07:00–16:00 UTC (London) and 12:00–21:00 UTC (New York)
- **FR-004**: System MUST check the real-time bid-ask spread before approving any trade signal
- **FR-005**: System MUST block any trade where the current spread exceeds the configured maximum spread threshold; spread MUST be measured in USD (dollar value) for XAUUSD — default threshold is $0.50 USD
- **FR-006**: System MUST load and parse a high-impact economic news calendar and maintain awareness of upcoming events
- **FR-007**: System MUST block trades within a configurable pre-event window (default: 30 minutes) before any high-impact news event
- **FR-008**: System MUST block trades within a configurable post-event window (default: 15 minutes) after any high-impact news event
- **FR-009**: System MUST classify the current volatility regime as LOW, NORMAL, or EXTREME based on recent price range data
- **FR-010**: System MUST block trades when the volatility regime is LOW or EXTREME
- **FR-011**: System MUST apply all filters in sequence; a trade signal requires ALL filters to return ALLOWED
- **FR-012**: System MUST log every filter decision (ALLOWED/BLOCKED) with: timestamp, signal ID (sourced from Spec 002 — SMC Engine), filter name, reason, and relevant metric value
- **FR-013**: System MUST expose configurable parameters for all thresholds (session windows, spread limit, news blackout windows, volatility bounds) via configuration file
- **FR-014**: System MUST handle DST transitions correctly for both London (GMT/BST) and New York (EST/EDT) sessions
- **FR-015**: System MUST fail safe — if any filter encounters an error (e.g., news calendar unavailable), it defaults to BLOCKED

### Key Entities

- **SessionWindow**: Represents a named trading session with UTC start/end times, DST-aware, and enabled/disabled status
- **FilterDecision**: Result of a single filter evaluation — contains: filter name, result (ALLOWED/BLOCKED), reason code, metric value, and timestamp
- **TradeGateResult**: Aggregated result of all filters for one signal — contains: signal ID, final result, list of individual FilterDecisions, evaluation timestamp
- **NewsEvent**: A scheduled economic event — contains: event name, impact level (HIGH/MEDIUM/LOW), scheduled UTC datetime, and affected currency pairs
- **VolatilityReading**: Current market volatility state — contains: regime (LOW/NORMAL/EXTREME), current ATR value, reference ATR value, ratio, and timestamp

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Filter evaluation for any signal completes in under 100 milliseconds, adding no meaningful latency to the trade decision pipeline
- **SC-002**: Zero trades are executed during blocked windows (Asian session, news blackout, extreme volatility, wide spread) — verified against logs over a 30-day period
- **SC-003**: All filter decisions are logged with 100% completeness — every signal evaluated produces a traceable FilterDecision record
- **SC-004**: Session classification is accurate for 100% of test cases across all DST transition scenarios (spring-forward and fall-back for both UK and US)
- **SC-005**: When the news calendar is unavailable, the system defaults to BLOCKED within 1 second and logs the failure — no silent pass-through
- **SC-006**: Configuring any filter threshold (spread limit, session times, news blackout duration) requires only a configuration file change and system restart — no code changes needed
- **SC-007**: Unit test coverage for all filter logic is ≥ 80%

---

## Assumptions

- News calendar data is sourced from an external provider (e.g., ForexFactory, Investing.com) or a locally maintained file; the exact source is a planning-phase decision
- Session boundaries use standard Forex market hours; Gold (XAUUSD) follows London and NY sessions primarily
- Volatility regime classification uses ATR (Average True Range) as the underlying metric, consistent with Spec 006 (ATR Calibration); exact thresholds will be defined during planning
- The spread threshold default is $0.50 USD for XAUUSD; spread is always expressed in USD (dollar value), not points — this is a starting value and will be tuned through backtesting
- DST transitions for London are last Sunday of March (GMT→BST) and last Sunday of October (BST→GMT); for New York, second Sunday of March (EST→EDT) and first Sunday of November (EDT→EST)
- Session windows are defined in LOCAL market hours with named IANA timezones (London: 08:00–17:00 Europe/London; New York: 08:00–17:00 America/New_York); UTC-equivalent times in FR-003 are approximate summer values — actual DST-aware boundaries are computed at runtime via zoneinfo; the broker MT5 terminal may report server time in a different timezone — conversion to UTC is the caller's responsibility before passing to evaluate_filters()

---

## Out of Scope

- Signal generation (covered in Spec 002 — SMC Engine)
- Lot sizing and risk management (covered in Spec 003 — Risk Management)
- ML-based volatility prediction (covered in Spec 007 — ML Signal Filter)
- Dynamic ATR threshold calibration (covered in Spec 006 — ATR Calibration)
- Order execution (covered in Spec 005 — Execution Engine)
