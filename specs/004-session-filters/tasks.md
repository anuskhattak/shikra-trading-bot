# Tasks: Session & Pre-Trade Filters

**Input**: Design documents from `specs/004-session-filters/`
**Branch**: `004-session-filters`
**Date**: 2026-05-19
**Prerequisites**: plan.md ✅ | spec.md ✅ | data-model.md ✅ | research.md ✅ | quickstart.md ✅

**Tests**: Included — SC-007 requires ≥ 80% unit test coverage for all filter modules.

**Organization**: Tasks grouped by user story. Each filter is independently implementable and testable. All filter modules (session, spread, news, volatility) are independent of each other — parallelizable after Phase 1.

---

## Dependencies & Execution Order

```
Phase 1 (Setup & Models) — BLOCKS all phases
    ↓
Phase 2 (US1: session_filter) ─┐
Phase 3 (US2: spread_filter)   ├─ fully parallel after Phase 1
Phase 4 (US3: news_filter)     ├─ fully parallel after Phase 1
Phase 5 (US4: volatility)      ┘
    ↓ all complete
Phase 6 (Orchestrator: trade_gate) — BLOCKS Polish
    ↓
Phase 7 (Polish & Coverage)
```

**Parallel opportunities**: T002/T003 within Phase 1; test tasks T005/T007/T009/T011 in parallel; all of Phase 2–5 in parallel; T017/T018/T019 in Phase 7.

---

## Phase 1: Setup & Models (Blocking)

**Purpose**: Data model and infrastructure — prerequisite for ALL filter phases.

- [x] T001 Create `src/filters/` directory with empty `__init__.py` placeholder
- [x] T002 [P] Update `config.yaml` — replace existing `sessions:` section (london/new_york: local_open="08:00", local_close="17:00", timezone, enabled) and add `filters:` section (spread max_spread_usd=0.50; news pre_event_minutes=30/post_event_minutes=15/calendar_path/impact_levels; volatility atr_lookback=14/low_atr_ratio=0.50/extreme_atr_ratio=5.0) and add `filters_log: logs/filter_decisions.json` to existing `logging:` section
- [x] T003 [P] Create `data/news_calendar.json` stub with 2–3 sample HIGH-impact events (schema from data-model.md); add `logs/filter_decisions.json` path to `.gitignore`
- [x] T004 Implement `src/filters/models.py` — enums (`FilterResult`, `SessionLabel`, `VolatilityRegime`, `NewsImpact`) and dataclasses (`SessionWindow`, `FilterDecision`, `TradeGateResult`, `NewsEvent`, `VolatilityReading`) with all fields from data-model.md

**Checkpoint**: `from src.filters.models import FilterResult, TradeGateResult, NewsEvent` imports without error.

---

## Phase 2: US1 — Session Window Enforcement (P1)

**Goal**: Bot detects the current trading session from UTC time and returns ALLOWED/BLOCKED with correct session label — including DST-aware London and New York windows.

**Independent Test**: `pytest tests/unit/test_filters_session.py` — all tests pass with no MT5 dependency.

### Tests first (must FAIL before implementation)

- [x] T005 [P] [US1] Write failing unit tests in `tests/unit/test_filters_session.py`:
  - `test_london_ny_overlap_allowed` — UTC 13:30 → LONDON_NY_OVERLAP, ALLOWED (US1 Scenario 1)
  - `test_asian_session_blocked` — UTC 04:00 → ASIAN_SESSION_EXCLUDED, BLOCKED (US1 Scenario 2)
  - `test_london_session_allowed` — UTC 08:30 → LONDON, ALLOWED (US1 Scenario 3)
  - `test_saturday_blocked` — Saturday UTC → MARKET_CLOSED, BLOCKED (US1 Scenario 4)
  - `test_sunday_blocked` — Sunday UTC → MARKET_CLOSED, BLOCKED (FR-002)
  - `test_holiday_christmas_blocked` — Dec 25 any year → MARKET_CLOSED (FR-002)
  - `test_holiday_good_friday_blocked` — Good Friday (computed date) → MARKET_CLOSED (FR-002)
  - `test_post_ny_gap_closed` — UTC 22:00 weekday → MARKET_CLOSED, BLOCKED (FR-001 edge case)
  - `test_session_boundary_exclusive_end` — UTC 16:00:00 exactly → NOT LONDON (inclusive start, exclusive end from spec Edge Cases)
  - `test_dst_london_summer_shifts_window` — BST summer: London opens at 07:00 UTC (not 08:00) (FR-014)
  - `test_dst_ny_summer_shifts_window` — EDT summer: NY opens at 12:00 UTC (not 13:00) (FR-014)

### Implementation

- [x] T006 [US1] Implement `src/filters/session_filter.py`:
  - `get_current_session(now_utc: datetime, config: dict) -> SessionLabel` — parses config into `SessionWindow` objects; uses `zoneinfo.ZoneInfo` for London (08:00–17:00 Europe/London) and NY (08:00–17:00 America/New_York) windows (D-002); detects LONDON_NY_OVERLAP dynamically (D-003); `holidays.country_holidays("GB")` for holiday check (D-009); post-NY gap 21:00–00:00 UTC → CLOSED (FR-001)
  - `check_session(now_utc: datetime, config: dict) -> FilterDecision` — wraps get_current_session; returns ALLOWED for LONDON/NEW_YORK/LONDON_NY_OVERLAP, BLOCKED otherwise
  - **Caller note**: `now_utc` must be UTC-aware (`datetime.now(timezone.utc)`); MT5 server time must be converted to UTC by caller before passing in (U3)

**Checkpoint**: `pytest tests/unit/test_filters_session.py` — all 11 tests pass.

---

## Phase 3: US2 — Spread Filter (P1)

**Goal**: Block trade when real-time XAUUSD spread exceeds the configured USD threshold.

**Independent Test**: `pytest tests/unit/test_filters_spread.py` — all tests pass.

### Tests first (must FAIL before implementation)

- [x] T007 [P] [US2] Write failing unit tests in `tests/unit/test_filters_spread.py`:
  - `test_spread_below_threshold_allowed` — spread=$0.30, threshold=$0.50 → ALLOWED (US2 Scenario 1)
  - `test_spread_above_threshold_blocked` — spread=$1.20, threshold=$0.50 → SPREAD_TOO_WIDE, BLOCKED (US2 Scenario 2)
  - `test_spread_config_threshold_applied` — custom threshold=$0.80 in config → $0.70 passes (US2 Scenario 3)
  - `test_spread_at_exact_threshold_allowed` — spread=$0.50 == threshold=$0.50 → ALLOWED (spec says "exceeds", so equal is NOT blocked); and `test_spread_one_cent_over_blocked` — spread=$0.51 → BLOCKED (A1)
  - `test_spread_zero_invalid_blocked` — spread=0.0 → INVALID_SPREAD, BLOCKED (Edge case from spec)
  - `test_spread_negative_invalid_blocked` — spread=-0.10 → INVALID_SPREAD, BLOCKED (Edge case from spec)
  - `test_spread_metric_value_logged` — spread=$0.28 → FilterDecision.metric_value == 0.28 (FR-012)

### Implementation

- [x] T008 [US2] Implement `src/filters/spread_filter.py`:
  - `check_spread(spread_usd: float, config: dict) -> FilterDecision` — reads `config["filters"]["spread"]["max_spread_usd"]`; spread ≤ 0 → INVALID_SPREAD BLOCKED (D-004); spread > threshold → SPREAD_TOO_WIDE BLOCKED; logs metric_value = spread_usd (FR-005, FR-012)

**Checkpoint**: `pytest tests/unit/test_filters_spread.py` — all 7 tests pass.

---

## Phase 4: US3 — News Event Filter (P2)

**Goal**: Block trades within pre/post blackout windows around HIGH-impact economic events; fail safe when calendar is missing.

**Independent Test**: `pytest tests/unit/test_filters_news.py` — all tests pass.

### Tests first (must FAIL before implementation)

- [x] T009 [P] [US3] Write failing unit tests in `tests/unit/test_filters_news.py`:
  - `test_pre_event_window_blocked` — NFP at 12:30, signal at 12:05 → NEWS_BLACKOUT_PRE_EVENT, BLOCKED (US3 Scenario 1)
  - `test_post_event_window_blocked` — NFP at 12:30, signal at 12:45 → NEWS_BLACKOUT_POST_EVENT, BLOCKED (US3 Scenario 2)
  - `test_no_event_in_window_allowed` — no HIGH event in ±window → ALLOWED (US3 Scenario 3)
  - `test_empty_calendar_blocked` — events=[] → NEWS_CALENDAR_UNAVAILABLE, BLOCKED (US3 Scenario 4, FR-015)
  - `test_outside_both_windows_allowed` — signal 45 min before event → ALLOWED
  - `test_medium_impact_event_ignored` — MEDIUM impact event in window → ALLOWED (only HIGH triggers; FR-006)
  - `test_load_calendar_valid_json` — `load_news_calendar("data/news_calendar.json")` returns `list[NewsEvent]`
  - `test_load_calendar_file_missing_returns_empty` — non-existent path → returns `[]` (FR-015 fail-safe)
  - `test_load_calendar_invalid_json_returns_empty` — malformed JSON → returns `[]` (FR-015 fail-safe)

### Implementation

- [x] T010 [US3] Implement `src/filters/news_filter.py`:
  - `load_news_calendar(filepath: str) -> list[NewsEvent]` — reads JSON; returns `[]` on missing file, parse error, or invalid schema (FR-015 fail-safe; D-006)
  - `check_news(now_utc: datetime, events: list[NewsEvent], config: dict) -> FilterDecision` — empty events → NEWS_CALENDAR_UNAVAILABLE BLOCKED; scans events where `impact in config impact_levels`; pre-event window → NEWS_BLACKOUT_PRE_EVENT; post-event window → NEWS_BLACKOUT_POST_EVENT (FR-007, FR-008)

**Checkpoint**: `pytest tests/unit/test_filters_news.py` — all 9 tests pass.

---

## Phase 5: US4 — Volatility Regime Pre-Filter (P2)

**Goal**: Classify current ATR ratio as LOW/NORMAL/EXTREME and block trades in abnormal regimes.

**Independent Test**: `pytest tests/unit/test_filters_volatility.py` — all tests pass.

### Tests first (must FAIL before implementation)

- [x] T011 [P] [US4] Write failing unit tests in `tests/unit/test_filters_volatility.py`:
  - `test_low_regime_blocked` — current_atr=5.0, ref=15.0, ratio=0.33 → VOLATILITY_TOO_LOW, BLOCKED (US4 Scenario 1)
  - `test_extreme_regime_blocked` — current_atr=80.0, ref=15.0, ratio=5.33 → VOLATILITY_EXTREME, BLOCKED (US4 Scenario 2)
  - `test_normal_regime_allowed` — current_atr=14.0, ref=13.0, ratio=1.07 → NORMAL, ALLOWED (US4 Scenario 3)
  - `test_extreme_boundary_at_5x` — ratio=5.0 exactly → EXTREME (FR-010)
  - `test_low_boundary_at_0_5x` — ratio=0.5 exactly → NORMAL (just at threshold — not LOW)
  - `test_classify_low` — ratio=0.3 → VolatilityRegime.LOW
  - `test_classify_normal` — ratio=1.5 → VolatilityRegime.NORMAL
  - `test_classify_extreme` — ratio=6.0 → VolatilityRegime.EXTREME
  - `test_metric_value_is_ratio` — FilterDecision.metric_value == ATR ratio (float), not regime string (I6/FR-012)
  - `test_classify_regime_returns_volatility_reading` — classify_regime() returns VolatilityReading with all 5 fields populated (I3)

### Implementation

- [x] T012 [US4] Implement `src/filters/volatility_filter.py`:
  - `classify_regime(current_atr: float, reference_atr: float, config: dict) -> VolatilityReading` — returns full VolatilityReading (regime, current_atr, reference_atr, ratio, timestamp); ratio = current/reference; LOW if ratio < low_atr_ratio; EXTREME if ratio ≥ extreme_atr_ratio; NORMAL otherwise (D-007, I3)
  - `check_volatility(current_atr: float, reference_atr: float, config: dict) -> FilterDecision` — calls classify_regime(); LOW → VOLATILITY_TOO_LOW BLOCKED; EXTREME → VOLATILITY_EXTREME BLOCKED; NORMAL → ALLOWED; metric_value = ratio float (FR-009, FR-010, FR-012)
  - **Note**: cooldown after EXTREME is descoped — deferred to Spec 006 (I4)

**Checkpoint**: `pytest tests/unit/test_filters_volatility.py` — all 9 tests pass.

---

## Phase 6: Orchestrator + Integration Tests (All Stories)

**Goal**: Wire all four filters into single entry point `evaluate_filters()` — short-circuit on first BLOCKED, fail-safe on exceptions, log every `TradeGateResult`.

**Independent Test**: `pytest tests/unit/test_filters_trade_gate.py tests/integration/test_filters_pipeline.py` — all tests pass.

### Tests first (must FAIL before implementation)

- [x] T013 [P] Write failing unit tests in `tests/unit/test_filters_trade_gate.py`:
  - `test_all_filters_pass_returns_allowed` — all 4 filters pass → ALLOWED, 4 decisions in result (FR-011, SC-001)
  - `test_session_block_short_circuits` — session BLOCKED → only 1 FilterDecision, final BLOCKED (D-001)
  - `test_spread_block_after_session_pass` — session ALLOWED, spread BLOCKED → 2 decisions (D-001)
  - `test_news_block_produces_3_decisions` — session+spread pass, news BLOCKED → 3 decisions
  - `test_each_decision_has_correct_fields` — filter_name, result, reason, metric_value, timestamp all present (FR-012)
  - `test_filter_exception_produces_filter_error` — session raises exception → FILTER_ERROR, BLOCKED (D-008, FR-015)
  - `test_trade_gate_result_signal_id_preserved` — signal_id in TradeGateResult matches input

- [x] T013c [P] Write failing SC-001 timing test in `tests/unit/test_filters_trade_gate.py`:
  - `test_evaluate_filters_completes_within_100ms` — call evaluate_filters() with valid inputs; assert elapsed time < 0.1s using `time.perf_counter()` (SC-001, U1)

- [x] T013b [P] Write failing integration tests in `tests/integration/test_filters_pipeline.py`:
  - `test_full_pipeline_allowed` — all valid inputs → TradeGateResult.final_result == ALLOWED
  - `test_full_pipeline_blocked_by_session` — Asian hour → BLOCKED, reason=ASIAN_SESSION_EXCLUDED
  - `test_full_pipeline_blocked_by_spread` — spread=$2.00 in London session → BLOCKED, reason=SPREAD_TOO_WIDE
  - `test_full_pipeline_blocked_by_news` — signal within news window → BLOCKED, reason=NEWS_BLACKOUT_PRE_EVENT
  - `test_full_pipeline_blocked_by_volatility` — extreme ATR → BLOCKED, reason=VOLATILITY_EXTREME

### Implementation

- [x] T014 Implement `src/filters/trade_gate.py`:
  - `evaluate_filters(signal_id, now_utc, spread_usd, news_events, current_atr, reference_atr, config) -> TradeGateResult` — runs session → spread → news → volatility in order (D-001); each wrapped in try/except → FILTER_ERROR on exception (D-008); short-circuits on first BLOCKED; appends completed TradeGateResult as JSON line to `config["logging"]["filters_log"]` path (FR-012); silent fail on write error
  - **signal_id note**: caller passes `str(uuid.uuid4())` — `EntrySignal` (spec002) has no built-in signal_id field; caller generates UUID per signal evaluation (I5)

**Checkpoint**: `pytest tests/unit/test_filters_trade_gate.py tests/integration/test_filters_pipeline.py` — all tests pass.

---

## Phase 7: Polish & Coverage

- [x] T015 Update `src/filters/__init__.py` — export public API: `evaluate_filters`, `load_news_calendar`, `TradeGateResult`, `FilterDecision`, `FilterResult`
- [x] T016 [P] Create `logs/filter_decisions.json` placeholder file; add to `.gitignore`
- [x] T017 [P] Run `pytest --cov=src/filters --cov-report=term-missing` — confirm ≥ 80% coverage across all modules (SC-007)
- [x] T018 [P] Run `grep -r "MetaTrader5\|import mt5" src/filters/` — must return zero results (broker-agnostic guarantee from D-004/D-005)
- [x] T019 Create `specs/004-session-filters/checklists/implementation-review.md` — mark all FR items checked after implementation

---

## Task Summary

| Phase | User Story | Tasks | Count |
|-------|-----------|-------|-------|
| Phase 1 — Setup & Models | — | T001–T004 | 4 |
| Phase 2 — Session Filter | US1 | T005–T006 | 2 |
| Phase 3 — Spread Filter | US2 | T007–T008 | 2 |
| Phase 4 — News Filter | US3 | T009–T010 | 2 |
| Phase 5 — Volatility Filter | US4 | T011–T012 | 2 |
| Phase 6 — Orchestrator | All | T013, T013b, T013c, T014 | 4 |
| Phase 7 — Polish | — | T015–T019 | 5 |
| **Total** | | | **21** |

---

## Implementation Strategy

### MVP (US1 + US2 — P1 filters only)

1. Complete Phase 1 (Setup & Models)
2. Complete Phase 2 (US1: `session_filter.py`)
3. Complete Phase 3 (US2: `spread_filter.py`)
4. **Validate**: `pytest tests/unit/test_filters_session.py tests/unit/test_filters_spread.py`
5. Both P1 filters working independently — minimal viable gating achieved

### Full Delivery Order (P1 → P2 → Orchestrator)

1. Phase 1 — Models (blocking)
2. Phase 2 + Phase 3 — US1 + US2: session + spread (P1; parallel if possible)
3. Phase 4 + Phase 5 — US3 + US4: news + volatility (P2; parallel if possible)
4. Phase 6 — Orchestrator wires all four
5. Phase 7 — Coverage + cleanup

### Notes

- Tests must be written and confirmed FAILING before implementation
- Each phase has an independent Checkpoint — validate before moving on
- No `import MetaTrader5` allowed in any `src/filters/` file
- All `datetime` values must be UTC-aware: use `datetime.now(timezone.utc)` not `datetime.utcnow()`
- `zoneinfo` requires `tzdata` package on Windows: `pip install tzdata`
- Session boundaries: inclusive start, exclusive end `[open, close)`
