# Research Notes: Session & Pre-Trade Filters

**Feature**: 004-session-filters
**Created**: 2026-05-19

---

## DST Handling — `zoneinfo` vs `pytz`

**Decision**: `zoneinfo` (Python 3.9+ stdlib)

**Rationale**: `zoneinfo` ships with Python 3.9+ — no extra pip install. It uses the IANA timezone database (`tzdata`). API is clean: `datetime.now(ZoneInfo("Europe/London"))`. The Python packaging guide recommends `zoneinfo` for new projects on Python 3.9+.

**Alternatives considered**:
- `pytz`: Third-party package; requires `.localize()` for DST-correct assignment — a known footgun. Adds a dependency. Superseded by `zoneinfo` for modern Python.
- Manual UTC offset table: Would require hardcoding DST start/end dates each year. The spec lists DST dates (last Sunday of March, etc.) but using named IANA zones makes this permanently correct with zero maintenance.

**IANA zone names used**:
- London: `"Europe/London"` — handles GMT (UTC+0) / BST (UTC+1) automatically
- New York: `"America/New_York"` — handles EST (UTC-5) / EDT (UTC-4) automatically

---

## Holiday Detection — `holidays` Library

**Decision**: `holidays.country_holidays("GB")` for UK market holidays

**Rationale**: Good Friday and Easter Monday are computed dates (Easter varies year to year). The `holidays` library calculates these correctly for any year. All five spec-required holidays are covered by `holidays.GB`:
- New Year's Day (Jan 1) ✓
- Good Friday ✓ (variable)
- Easter Monday ✓ (variable)
- Christmas Day (Dec 25) ✓
- Boxing Day (Dec 26) ✓

**Alternatives considered**:
- `python-dateutil` Easter algorithm: Could compute Good Friday/Easter Monday manually, but requires extra glue code. `holidays` wraps this cleanly.
- Hardcoded annual list: Fails for dynamic holidays and requires manual update every year.

---

## Session Window Design — LOCAL Time in Config

**Decision**: Store sessions as local market hours + named timezone in `config.yaml`

**Rationale**: Sessions represent when exchanges are open in LOCAL business hours. Storing fixed UTC times (e.g., `08:00 UTC`) would break when DST shifts — London's 08:00 local time is UTC+0 in winter but UTC+1 in summer. Storing local times with named timezones lets `zoneinfo` compute the current UTC equivalent at runtime, permanently DST-correct.

**Standard Forex market hours**:
- London: 08:00–16:00 Europe/London local time
- New York: 08:00–17:00 America/New_York local time

**Session boundary rule**: inclusive start, exclusive end — `[open, close)` — consistent with spec Edge Cases.

**Asian session**: Not traded for XAUUSD. Classified as BLOCKED / ASIAN_SESSION_EXCLUDED. Boundary 00:00–07:00 UTC is fixed (no DST-relevant exchange).

**Post-NY gap** (21:00–00:00 UTC): CLOSED — no session is open after NY close, before Asian open.

---

## Spread Measurement for XAUUSD

**Decision**: `spread_usd = ask - bid` (directly in USD, no conversion)

**Rationale**: XAUUSD is quoted in USD per troy ounce. Both ask and bid prices are USD floats. The difference is already the dollar spread — no pip conversion or multiplier needed. This is different from forex pairs (e.g., EURUSD) where spread requires pip-value conversion.

**Caller source**:
```python
info = mt5.symbol_info("XAUUSD")
spread_usd = info.ask - info.bid
```

**Invalid spread handling**: If `spread_usd <= 0`, filter returns BLOCKED with reason `INVALID_SPREAD` (FR-015 fail-safe — zero spread is a broker data error).

---

## ATR Volatility Reference Period

**Decision**: `current_atr` = ATR(14) on H1 candles; `reference_atr` = 50-bar rolling mean of ATR(14) values on H1

**Rationale**:
- H1 is the entry timeframe for this bot (consistent with SMC engine ltf = H1)
- ATR(14) is the standard Wilder period — widely used, config-tunable
- Reference ATR as a 50-bar rolling mean gives a stable baseline of "normal" intraday volatility
- Ratio = `current_atr / reference_atr`; thresholds: LOW < 0.5, NORMAL [0.5, 5.0), EXTREME ≥ 5.0
- Same OHLCV fetch used by SMC engine — no additional broker call required

**Config**: `atr_lookback: 14` applies to both current and reference ATR calculations.

---

## News Calendar — Local JSON File (v1)

**Decision**: Local file at `data/news_calendar.json`; loaded by caller once at startup

**Rationale**: Eliminates any network dependency inside the filter module — fully testable offline. The filter module's API (`check_news(now_utc, events, config)`) accepts a pre-loaded list, decoupling I/O from logic. Fail-safe (FR-015): if the file is missing or unparseable, `load_news_calendar()` returns an empty list and the caller logs the failure; `check_news()` with empty list returns BLOCKED with `NEWS_CALENDAR_UNAVAILABLE`.

**Future upgrade path**: API-based calendar refresh is an upgrade to the caller layer only — the filter API does not change.

**JSON schema**:
```json
[
  {
    "name": "US Non-Farm Payrolls",
    "impact": "HIGH",
    "scheduled_utc": "2026-06-06T12:30:00Z",
    "currencies": ["USD", "XAU"]
  }
]
```

Only `impact = "HIGH"` events trigger blackouts by default (configurable via `impact_levels` in config).
