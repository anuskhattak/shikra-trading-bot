# Implementation Review Checklist: Session & Pre-Trade Filters

**Purpose**: Track which spec requirements are implemented in code vs missing
**Created**: 2026-05-19
**Feature**: [spec.md](../spec.md)
**Code Under Review**: `src/filters/models.py`, `src/filters/session_filter.py`, `src/filters/spread_filter.py`, `src/filters/news_filter.py`, `src/filters/volatility_filter.py`, `src/filters/trade_gate.py`

**Legend**: `[x]` = Done | `[ ]` = Missing | `[~]` = Partial / Gap

---

## Models — `src/filters/models.py`

- [x] CHK001 — T004: Enums defined — `FilterResult` (ALLOWED, BLOCKED), `SessionLabel` (ASIAN, LONDON, NEW_YORK, LONDON_NY_OVERLAP, CLOSED), `VolatilityRegime` (LOW, NORMAL, EXTREME), `NewsImpact` (HIGH, MEDIUM, LOW) [data-model.md §Enums]
- [x] CHK001b — T004: `SessionWindow` dataclass defined with fields: name, local_open, local_close, timezone, enabled [data-model.md §SessionWindow, plan.md §D-002]
- [x] CHK002 — T004: `FilterDecision` dataclass defined with fields: filter_name, result, reason, metric_value (float|str), timestamp [data-model.md §FilterDecision]
- [x] CHK003 — T004: `TradeGateResult` dataclass defined with fields: signal_id, final_result, decisions (list[FilterDecision]), evaluated_at [data-model.md §TradeGateResult]
- [x] CHK004 — T004: `NewsEvent` and `VolatilityReading` dataclasses defined with all fields from data-model.md; `VolatilityReading` is the return type of `classify_regime()` [data-model.md §NewsEvent, §VolatilityReading]

---

## Session Filter — `src/filters/session_filter.py`

- [x] CHK005 — T006/FR-001: `get_current_session()` returns correct `SessionLabel` for all five states (ASIAN, LONDON, NEW_YORK, LONDON_NY_OVERLAP, CLOSED); post-NY gap 21:00–00:00 UTC classified as CLOSED [Spec §FR-001]
- [x] CHK006 — T006/FR-002: Asian session (00:00–07:00 UTC), post-NY gap (21:00–00:00 UTC), weekends (Sat/Sun) all return BLOCKED with reason `ASIAN_SESSION_EXCLUDED` or `MARKET_CLOSED` [Spec §FR-002]
- [x] CHK007 — T006/FR-002: Major holidays (New Year's Day, Good Friday, Easter Monday, Christmas Day, Boxing Day) detected via `holidays.country_holidays("GB")` → MARKET_CLOSED [Spec §FR-002, plan.md §D-009]
- [x] CHK008 — T006/FR-003: London (08:00–17:00 Europe/London), New York (08:00–17:00 America/New_York), and LONDON_NY_OVERLAP (both simultaneously open) return ALLOWED [Spec §FR-003]
- [x] CHK009 — T006/FR-014: Session windows use `zoneinfo.ZoneInfo` with named IANA timezones — DST transitions for London (GMT/BST) and New York (EST/EDT) handled automatically; sessions defined in LOCAL time (not fixed UTC); `now_utc` must be UTC-aware datetime from caller [Spec §FR-014, plan.md §D-002]
- [x] CHK010 — T006: Session boundary uses inclusive start, exclusive end `[open, close)` — exactly at `close` time is NOT in session [Spec §Edge Cases]
- [x] CHK011 — T006/D-003: LONDON_NY_OVERLAP is computed dynamically (both sessions open simultaneously) — not a separately configured session [plan.md §D-003]

---

## Spread Filter — `src/filters/spread_filter.py`

- [x] CHK012 — T008/FR-004: `check_spread()` reads real-time `spread_usd` passed by caller [Spec §FR-004]
- [x] CHK013 — T008/FR-005: Trade blocked when `spread_usd > max_spread_usd`; reason = `SPREAD_TOO_WIDE`; metric_value = spread_usd logged (FR-012) [Spec §FR-005]
- [x] CHK014 — T008: Invalid spread (≤ 0) returns BLOCKED with reason `INVALID_SPREAD` [Spec §Edge Cases]

---

## News Filter — `src/filters/news_filter.py`

- [x] CHK015 — T010/FR-006: `load_news_calendar(filepath)` loads JSON file and returns `list[NewsEvent]`; returns `[]` on missing file, parse error, or invalid schema (fail-safe, FR-015) [Spec §FR-006, plan.md §D-006]
- [x] CHK016 — T010/FR-007: `check_news()` blocks within `pre_event_minutes` before any HIGH-impact event; reason = `NEWS_BLACKOUT_PRE_EVENT` [Spec §FR-007]
- [x] CHK017 — T010/FR-008: `check_news()` blocks within `post_event_minutes` after any HIGH-impact event; reason = `NEWS_BLACKOUT_POST_EVENT` [Spec §FR-008]
- [x] CHK018 — T010/FR-015: Empty `events` list → BLOCKED with reason `NEWS_CALENDAR_UNAVAILABLE` (fail-safe) [Spec §FR-015, US3 Scenario 4]
- [x] CHK019 — T010: Only events with `impact` in `config impact_levels` (default: HIGH) trigger blackout; MEDIUM/LOW events are ignored [Spec §FR-006]

---

## Volatility Filter — `src/filters/volatility_filter.py`

- [x] CHK020 — T012/FR-009: `classify_regime()` returns `VolatilityReading` (not raw enum) — all 5 fields populated: regime, current_atr, reference_atr, ratio, timestamp [data-model.md §VolatilityReading]
- [x] CHK021 — T012/FR-009: `classify_regime()` sets regime=LOW when `current_atr / reference_atr < low_atr_ratio` (default 0.5) [Spec §FR-009, plan.md §D-007]
- [x] CHK022 — T012/FR-009: `classify_regime()` sets regime=EXTREME when ratio >= extreme_atr_ratio (default 5.0); regime=NORMAL for ratio in [low_atr_ratio, extreme_atr_ratio) [Spec §FR-009]
- [x] CHK023 — T012/FR-010: `check_volatility()` returns BLOCKED for LOW (`VOLATILITY_TOO_LOW`) and EXTREME (`VOLATILITY_EXTREME`); metric_value = ATR ratio float (not regime label string) [Spec §FR-010, FR-012]

---

## Orchestrator — `src/filters/trade_gate.py`

- [x] CHK024 — T014/FR-011: `evaluate_filters()` runs all 4 filters in sequence: session → spread → news → volatility [Spec §FR-011, plan.md §D-001]
- [x] CHK025 — T014/D-001: Short-circuit on first BLOCKED result — remaining filters not evaluated; `TradeGateResult.decisions` contains only evaluated filters [plan.md §D-001]
- [x] CHK026 — T014/FR-012: Every `TradeGateResult` logged to path from `config["logging"]["filters_log"]` as newline-delimited JSON; signal_id is UUID generated by caller (not from EntrySignal) [Spec §FR-012, data-model.md §Log Entry Format]
- [x] CHK027 — T014/FR-015: Each filter call wrapped in try/except; unhandled exception → BLOCKED `FilterDecision` with reason `FILTER_ERROR`; no exception propagates to caller [Spec §FR-015, plan.md §D-008]
- [x] CHK028 — T014: `TradeGateResult.final_result` is ALLOWED only when ALL evaluated filters return ALLOWED [Spec §FR-011]

---

## Non-Functional & Cross-Cutting

- [x] CHK029 — FR-013: All filter thresholds (session windows, spread limit, news blackout windows, volatility bounds) configurable via `config.yaml` — no hardcoded values [Spec §FR-013]
- [x] CHK030 — T018: No `MetaTrader5` or `import mt5` in any `src/filters/` module — broker-agnostic (plan.md §D-004, §D-005)
- [x] CHK031 — All `datetime` values are UTC-aware: `datetime.now(timezone.utc)` used throughout — NOT `datetime.utcnow()` (naive UTC)
- [x] CHK032 — All public functions have type hints and one-line docstrings

---

## Success Criteria

- [x] CHK033 — SC-001/T013c: `test_evaluate_filters_completes_within_100ms` passes — timing test using `time.perf_counter()` [Spec §SC-001]
- [x] CHK034 — SC-002: Zero trades execute during blocked windows — verified by TradeGateResult logs showing 100% BLOCKED rate during Asian session, news blackout, wide spread, extreme volatility [Spec §SC-002]
- [x] CHK035 — SC-003: Every call to `evaluate_filters()` produces a logged `TradeGateResult` entry — no silent failures [Spec §SC-003]
- [x] CHK036 — SC-004: Session classification passes all DST test cases (spring-forward and fall-back for UK and US) [Spec §SC-004]
- [x] CHK037 — SC-005: Empty news events list → BLOCKED within 1 second; failure logged with `NEWS_CALENDAR_UNAVAILABLE` [Spec §SC-005]
- [x] CHK038 — SC-006: Changing any threshold in `config.yaml` takes effect after system restart — no code changes needed [Spec §SC-006]
- [x] CHK039 — SC-007: `pytest --cov=src/filters` reports ≥ 80% coverage [Spec §SC-007]

---

## Infrastructure & Config

- [x] CHK040 — T015: `src/filters/__init__.py` exports public API: `evaluate_filters`, `load_news_calendar`, `TradeGateResult`, `FilterDecision`, `FilterResult`
- [x] CHK041 — T002: `config.yaml` contains `sessions:` section (london + new_york: local_open="08:00", local_close="17:00", timezone, enabled) and `filters:` section (spread/news/volatility) and `logging.filters_log: logs/filter_decisions.json`
- [x] CHK042 — T003: `data/news_calendar.json` stub exists with at least 2 HIGH-impact events in valid schema
- [x] CHK043 — T016: `logs/filter_decisions.json` path added to `.gitignore`

---

## Test Coverage

- [x] CHK044 — T005: `tests/unit/test_filters_session.py` exists with 11 tests (DST, holidays, boundaries, sessions)
- [x] CHK045 — T007: `tests/unit/test_filters_spread.py` exists with 7 tests (threshold, invalid spread, metric logging)
- [x] CHK046 — T009: `tests/unit/test_filters_news.py` exists with 9 tests (pre/post blackout, fail-safe, file load)
- [x] CHK047 — T011: `tests/unit/test_filters_volatility.py` exists with 9 tests (LOW/NORMAL/EXTREME boundaries, classify_regime)
- [x] CHK048 — T013: `tests/unit/test_filters_trade_gate.py` exists with 7 tests (short-circuit, all-pass, error path)
- [x] CHK049 — T013b: `tests/integration/test_filters_pipeline.py` exists with 5 tests (end-to-end pipeline)

---

## Summary

| Category | Total | Done ✅ | Partial ⚠️ | Missing ❌ |
|---|---|---|---|---|
| Models | 5 | 5 | 0 | 0 |
| Session Filter | 7 | 7 | 0 | 0 |
| Spread Filter | 3 | 3 | 0 | 0 |
| News Filter | 5 | 5 | 0 | 0 |
| Volatility Filter | 4 | 4 | 0 | 0 |
| Orchestrator | 5 | 5 | 0 | 0 |
| Non-Functional | 4 | 4 | 0 | 0 |
| Success Criteria | 7 | 7 | 0 | 0 |
| Infrastructure | 4 | 4 | 0 | 0 |
| Test Coverage | 6 | 6 | 0 | 0 |
| **Total** | **50** | **50** | **0** | **0** |

> Phase 1 complete (2026-05-19): T001–T004 done — models.py, config.yaml, data/news_calendar.json.
> Phase 2 complete (2026-05-19): T005–T006 done — session_filter.py, 11 tests pass.
> Phase 3 complete (2026-05-19): T007–T008 done — spread_filter.py, 8 tests pass.
> All 11 analysis findings from /sp.analyze resolved (2026-05-19).
> Phase 4 complete (2026-05-19): T009–T010 done — news_filter.py, 9 tests pass.
> Phase 5 complete (2026-05-19): T011–T012 done — volatility_filter.py, 10 tests pass.
> Phase 6 complete (2026-05-19): T013–T014 done — trade_gate.py, 8 unit + 5 integration tests pass (51 total).
> Phase 7 complete (2026-05-19): T015–T019 done — __init__.py exports, logs placeholder, 99% coverage, zero MT5 imports. ALL 50/50 CHK items complete.
