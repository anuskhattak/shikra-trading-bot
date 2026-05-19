# Implementation Plan: Session & Pre-Trade Filters

**Branch**: `004-session-filters` | **Date**: 2026-05-19 | **Spec**: [spec.md](spec.md)

---

## Objective

Build the `src/filters/` module — a broker-agnostic pre-trade gatekeeper that sits between the SMC engine output (`EntrySignal`) and the risk/execution pipeline. All four filters (Session, Spread, News, Volatility) run in sequence; a single BLOCKED result halts the trade. All logic testable without an MT5 connection.

---

## Architecture

```
EntrySignal (from spec002)
        │
        ▼
┌──────────────────────────────────┐
│       src/filters/               │
│                                  │
│  models.py                       │
│    FilterResult, SessionLabel    │
│    VolatilityRegime, NewsImpact  │
│    FilterDecision                │
│    TradeGateResult               │
│    NewsEvent                     │
│    VolatilityReading             │
│                                  │
│  session_filter.py               │
│    get_current_session()         │
│    check_session()               │
│                                  │
│  spread_filter.py                │
│    check_spread()                │
│                                  │
│  news_filter.py                  │
│    load_news_calendar()          │
│    check_news()                  │
│                                  │
│  volatility_filter.py            │
│    classify_regime()             │
│    check_volatility()            │
│                                  │
│  trade_gate.py  ← main entry     │
│    evaluate_filters()            │
│                                  │
└──────────────────────────────────┘
        │
        ▼
  TradeGateResult (ALLOWED / BLOCKED)
        │
        ▼
  spec005 — Execution Engine
```

---

## Key Design Decisions

### D-001: Filter Evaluation Order — Session → Spread → News → Volatility
Session check is pure datetime math (O(1)) — cheapest and highest block rate on weekends/Asian session. Spread is a real-time value passed by caller. News is an in-memory calendar lookup. Volatility requires ATR ratio computation. Cheapest-first with short-circuit on first BLOCKED satisfies SC-001 (<100ms).

### D-002: Sessions Defined in LOCAL Time — `zoneinfo` for DST
Sessions are configured as local market hours with named IANA timezone (e.g., London 08:00–16:00 `Europe/London`). `zoneinfo.ZoneInfo` (Python 3.9+ stdlib) converts UTC to local time at runtime — DST transitions for both London (GMT/BST) and New York (EST/EDT) are handled automatically. No manual offset maintenance required (FR-014).

### D-003: Overlap Detected Dynamically
`LONDON_NY_OVERLAP` is not a separate configured session. It is computed when the current UTC time falls within both the London AND New York session windows simultaneously. No extra config entry needed.

### D-004: Spread Passed as Parameter (Broker-Agnostic)
The spread filter receives `spread_usd: float` from the caller. `spread_usd = ask - bid` for XAUUSD (both prices are in USD — no conversion required). The filter module has zero MT5 dependency.

### D-005: ATR Values Passed as Parameters
`current_atr` and `reference_atr` are passed by the caller (main loop). The volatility filter does not fetch candles or compute ATR internally. Reference ATR = rolling 50-bar mean of ATR(14) on H1, sourced from the same OHLCV feed used by the SMC engine.

### D-006: News Calendar = Local JSON File (v1)
For v1, the news calendar is a local JSON file (`data/news_calendar.json`) loaded once by the caller at startup and passed as `list[NewsEvent]`. This eliminates network dependency inside the filter module. Future API-based refresh is an upgrade to the caller layer only — the filter API does not change.

### D-007: Volatility Thresholds — LOW < 0.5×, EXTREME ≥ 5.0×
"Significantly below average" = `current_atr < 0.5 × reference_atr` (LOW).
"5× or more above average" = `current_atr >= 5.0 × reference_atr` (EXTREME) — matches spec FR-010 verbatim.
Both thresholds are configurable via `config.yaml` (FR-013).

### D-008: Fail-Safe Inside `evaluate_filters()`
Each sub-filter call is wrapped in `try/except` inside the orchestrator. Any unhandled exception produces a BLOCKED `FilterDecision` with reason `FILTER_ERROR`. No exception propagates to the caller — FR-015 fail-safe is guaranteed at the orchestrator level.

### D-009: Holiday Detection via `holidays` Library
Good Friday and Easter Monday are computed dates (not fixed). `holidays.country_holidays("GB")` covers all five spec-required holidays: New Year's Day, Good Friday, Easter Monday, Christmas Day, Boxing Day.

---

## Module Breakdown

### `src/filters/models.py`
- Enums: `FilterResult` (ALLOWED, BLOCKED), `SessionLabel` (ASIAN, LONDON, NEW_YORK, LONDON_NY_OVERLAP, CLOSED), `VolatilityRegime` (LOW, NORMAL, EXTREME), `NewsImpact` (HIGH, MEDIUM, LOW)
- `SessionWindow` dataclass: `name: str`, `local_open: str`, `local_close: str`, `timezone: str`, `enabled: bool` — parsed from config; used internally by session_filter.py
- `FilterDecision` dataclass: `filter_name`, `result`, `reason`, `metric_value: float | str`, `timestamp`
- `TradeGateResult` dataclass: `signal_id`, `final_result`, `decisions: list[FilterDecision]`, `evaluated_at`
- `NewsEvent` dataclass: `name`, `impact: NewsImpact`, `scheduled_utc: datetime`, `currencies: list[str]`
- `VolatilityReading` dataclass: `regime`, `current_atr`, `reference_atr`, `ratio`, `timestamp` — returned by `classify_regime()`

### `src/filters/session_filter.py`
- `get_current_session(now_utc: datetime, config: dict) -> SessionLabel`
- `check_session(now_utc: datetime, config: dict) -> FilterDecision`

### `src/filters/spread_filter.py`
- `check_spread(spread_usd: float, config: dict) -> FilterDecision`

### `src/filters/news_filter.py`
- `load_news_calendar(filepath: str) -> list[NewsEvent]`
- `check_news(now_utc: datetime, events: list[NewsEvent], config: dict) -> FilterDecision`

### `src/filters/volatility_filter.py`
- `classify_regime(current_atr: float, reference_atr: float, config: dict) -> VolatilityReading`
- `check_volatility(current_atr: float, reference_atr: float, config: dict) -> FilterDecision`

### `src/filters/trade_gate.py`  ← main entry point
- `evaluate_filters(signal_id: str, now_utc: datetime, spread_usd: float, news_events: list[NewsEvent], current_atr: float, reference_atr: float, config: dict) -> TradeGateResult`
- Runs: session → spread → news → volatility; short-circuits on first BLOCKED (D-001)
- Each filter wrapped in try/except; exception → BLOCKED with `FILTER_ERROR` (D-008)
- Logs completed `TradeGateResult` to `logs/filter_decisions.json` (FR-012)

### `src/filters/__init__.py`
- Exports: `evaluate_filters`, `load_news_calendar`, `TradeGateResult`, `FilterDecision`, `FilterResult`

---

## Config Updates (`config.yaml`)

Existing `sessions:` section replaced; new `filters:` section added:

```yaml
sessions:
  london:
    local_open: "08:00"
    local_close: "17:00"
    timezone: "Europe/London"
    enabled: true
  new_york:
    local_open: "08:00"
    local_close: "17:00"
    timezone: "America/New_York"
    enabled: true

filters:
  spread:
    max_spread_usd: 0.50
  news:
    pre_event_minutes: 30
    post_event_minutes: 15
    calendar_path: "data/news_calendar.json"
    impact_levels: ["HIGH"]
  volatility:
    atr_lookback: 14
    low_atr_ratio: 0.50
    extreme_atr_ratio: 5.0

logging:
  filters_log: logs/filter_decisions.json
```

---

## Test Strategy

### Unit Tests
- `tests/unit/test_filters_session.py` — FR-001, FR-002, FR-003, FR-014 (DST spring/fall scenarios)
- `tests/unit/test_filters_spread.py` — FR-004, FR-005 (normal, borderline, spike, invalid spread)
- `tests/unit/test_filters_news.py` — FR-006, FR-007, FR-008, FR-015 (file missing fail-safe)
- `tests/unit/test_filters_volatility.py` — FR-009, FR-010 (LOW, NORMAL, EXTREME, cooldown)
- `tests/unit/test_filters_trade_gate.py` — FR-011, FR-012, FR-013, FR-015 (short-circuit, all-pass, error path)

### Integration Tests
- `tests/integration/test_filters_pipeline.py` — end-to-end: EntrySignal → evaluate_filters → TradeGateResult

### Coverage Target
≥ 80% for all `src/filters/` modules (SC-007)

---

## Phased Delivery

```
Phase 1: models.py — enums + dataclasses (blocking dependency)
Phase 2: session_filter.py + tests (P1 — DST-aware session gating)
Phase 3: spread_filter.py + tests (P1 — spread check)
Phase 4: news_filter.py + tests (P2 — calendar load + blackout logic)
Phase 5: volatility_filter.py + tests (P2 — ATR regime classifier)
Phase 6: trade_gate.py + integration tests (orchestrator + fail-safe + logging)
Phase 7: config.yaml update, __init__.py, data/news_calendar.json stub, coverage check
```
