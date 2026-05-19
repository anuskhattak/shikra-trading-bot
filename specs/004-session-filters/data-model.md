# Data Model: Session & Pre-Trade Filters

**Feature**: 004-session-filters
**Created**: 2026-05-19

---

## Enums

```python
from enum import Enum

class FilterResult(Enum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"

class SessionLabel(Enum):
    ASIAN             = "ASIAN"
    LONDON            = "LONDON"
    NEW_YORK          = "NEW_YORK"
    LONDON_NY_OVERLAP = "LONDON_NY_OVERLAP"
    CLOSED            = "CLOSED"

class VolatilityRegime(Enum):
    LOW     = "LOW"
    NORMAL  = "NORMAL"
    EXTREME = "EXTREME"

class NewsImpact(Enum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"
```

---

## Dataclasses

### `SessionWindow` — Named session window parsed from config

```python
@dataclass
class SessionWindow:
    name:        str    # e.g. "london", "new_york"
    local_open:  str    # e.g. "08:00" (local market time)
    local_close: str    # e.g. "17:00" (local market time)
    timezone:    str    # IANA zone: "Europe/London" or "America/New_York"
    enabled:     bool
```

### `FilterDecision` — Result of one filter evaluation

```python
@dataclass
class FilterDecision:
    filter_name:  str              # "session", "spread", "news", "volatility"
    result:       FilterResult
    reason:       str              # Reason code — see table below
    metric_value: float | str      # e.g. 0.30 (spread), "LONDON_NY_OVERLAP" (session)
    timestamp:    datetime
```

### `TradeGateResult` — Aggregated result for one signal evaluation

```python
@dataclass
class TradeGateResult:
    signal_id:    str
    final_result: FilterResult              # ALLOWED only if ALL filters passed
    decisions:    list[FilterDecision]      # One entry per filter evaluated (may be < 4 on short-circuit)
    evaluated_at: datetime
```

### `NewsEvent` — One scheduled economic event

```python
@dataclass
class NewsEvent:
    name:          str         # e.g. "US Non-Farm Payrolls"
    impact:        NewsImpact  # HIGH / MEDIUM / LOW
    scheduled_utc: datetime    # timezone-aware UTC datetime
    currencies:    list[str]   # e.g. ["USD", "XAU"]
```

### `VolatilityReading` — ATR regime snapshot returned by `classify_regime()`

```python
@dataclass
class VolatilityReading:
    regime:        VolatilityRegime
    current_atr:   float
    reference_atr: float
    ratio:         float      # current_atr / reference_atr
    timestamp:     datetime
```

---

## Config Schema (`config.yaml` additions)

```yaml
sessions:
  london:
    local_open:  "08:00"           # London local time (Europe/London)
    local_close: "17:00"           # 17:00 London local = 16:00 UTC in summer (BST)
    timezone:    "Europe/London"
    enabled:     true
  new_york:
    local_open:  "08:00"           # New York local time (America/New_York)
    local_close: "17:00"           # 17:00 NY local = 21:00 UTC in summer (EDT)
    timezone:    "America/New_York"
    enabled:     true

filters:
  spread:
    max_spread_usd: 0.50            # Default $0.50 USD threshold (FR-005)
  news:
    pre_event_minutes:  30          # Block N min before HIGH-impact event (FR-007)
    post_event_minutes: 15          # Block N min after HIGH-impact event (FR-008)
    calendar_path: "data/news_calendar.json"
    impact_levels: ["HIGH"]         # Only HIGH events trigger blackout
  volatility:
    atr_lookback:       14          # Standard Wilder ATR period
    low_atr_ratio:      0.50        # ATR ratio below this = LOW regime
    extreme_atr_ratio:  5.0         # ATR ratio at/above this = EXTREME regime
    # cooldown_candles deferred to Spec 006 — ATR Calibration

logging:
  filters_log: logs/filter_decisions.json   # FR-012 filter decision audit trail
```

---

## Reason Codes (`FilterDecision.reason`)

| Filter | Reason Code | Trigger Condition |
|--------|-------------|-------------------|
| session | `ASIAN_SESSION_EXCLUDED` | UTC time in 00:00–07:00 window |
| session | `MARKET_CLOSED` | Weekend, major holiday, or 21:00–00:00 post-NY gap |
| session | `ALLOWED` | Active London / NY / Overlap window |
| spread | `SPREAD_TOO_WIDE` | `spread_usd > max_spread_usd` |
| spread | `INVALID_SPREAD` | `spread_usd <= 0` from broker |
| spread | `ALLOWED` | Spread within threshold |
| news | `NEWS_BLACKOUT_PRE_EVENT` | Within `pre_event_minutes` before HIGH-impact event |
| news | `NEWS_BLACKOUT_POST_EVENT` | Within `post_event_minutes` after HIGH-impact event |
| news | `NEWS_CALENDAR_UNAVAILABLE` | File missing, parse error, or empty list (fail-safe) |
| news | `ALLOWED` | No active blackout window |
| volatility | `VOLATILITY_TOO_LOW` | `current_atr / reference_atr < low_atr_ratio` |
| volatility | `VOLATILITY_EXTREME` | `current_atr / reference_atr >= extreme_atr_ratio` |
| volatility | `VOLATILITY_COOLDOWN` | Cooldown candles remaining after EXTREME regime |
| volatility | `ALLOWED` | ATR ratio in NORMAL range |
| any filter | `FILTER_ERROR` | Unhandled exception caught by orchestrator (fail-safe BLOCKED) |

---

## Key Entities (Caller's Responsibility)

The filters module does **not** fetch these — all passed as parameters to `evaluate_filters()`:

| Parameter | Source | Unit |
|-----------|--------|------|
| `signal_id` | `str(uuid.uuid4())` — generated by caller; `EntrySignal` has no built-in signal_id | str |
| `now_utc` | `datetime.now(timezone.utc)` — caller converts MT5 server time to UTC | UTC-aware datetime |
| `spread_usd` | `mt5.symbol_info("XAUUSD").ask - .bid` | USD float |
| `news_events` | `load_news_calendar(path)` called once at startup | `list[NewsEvent]` |
| `current_atr` | ATR(14) on H1 OHLCV — most recent bar | price units (float) |
| `reference_atr` | Rolling 50-bar mean of ATR(14) on H1 | price units (float) |

---

## Log Entry Format (`logs/filter_decisions.json`)

Each `TradeGateResult` is appended as a JSON object (newline-delimited):

```json
{
  "signal_id": "sig_20260519_143022_abc",
  "final_result": "ALLOWED",
  "evaluated_at": "2026-05-19T14:30:22Z",
  "decisions": [
    {
      "filter_name": "session",
      "result": "ALLOWED",
      "reason": "ALLOWED",
      "metric_value": "LONDON_NY_OVERLAP",
      "timestamp": "2026-05-19T14:30:22Z"
    },
    {
      "filter_name": "spread",
      "result": "ALLOWED",
      "reason": "ALLOWED",
      "metric_value": 0.28,
      "timestamp": "2026-05-19T14:30:22Z"
    },
    {
      "filter_name": "news",
      "result": "ALLOWED",
      "reason": "ALLOWED",
      "metric_value": "no_event",
      "timestamp": "2026-05-19T14:30:22Z"
    },
    {
      "filter_name": "volatility",
      "result": "ALLOWED",
      "reason": "ALLOWED",
      "metric_value": 0.88,
      "timestamp": "2026-05-19T14:30:22Z"
    }
  ]
}
```

Short-circuit example (session BLOCKED — spread/news/volatility not evaluated):

```json
{
  "signal_id": "sig_20260519_030011_xyz",
  "final_result": "BLOCKED",
  "evaluated_at": "2026-05-19T03:00:11Z",
  "decisions": [
    {
      "filter_name": "session",
      "result": "BLOCKED",
      "reason": "ASIAN_SESSION_EXCLUDED",
      "metric_value": "ASIAN",
      "timestamp": "2026-05-19T03:00:11Z"
    }
  ]
}
```

---

## News Calendar JSON Schema (`data/news_calendar.json`)

```json
[
  {
    "name": "US Non-Farm Payrolls",
    "impact": "HIGH",
    "scheduled_utc": "2026-06-06T12:30:00Z",
    "currencies": ["USD", "XAU"]
  },
  {
    "name": "FOMC Rate Decision",
    "impact": "HIGH",
    "scheduled_utc": "2026-06-11T18:00:00Z",
    "currencies": ["USD", "XAU"]
  },
  {
    "name": "US CPI",
    "impact": "HIGH",
    "scheduled_utc": "2026-06-10T12:30:00Z",
    "currencies": ["USD", "XAU"]
  }
]
```
