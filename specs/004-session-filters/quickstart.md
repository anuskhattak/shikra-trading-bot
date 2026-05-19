# Quickstart: Session & Pre-Trade Filters

**Feature**: 004-session-filters
**Created**: 2026-05-19

---

## Step 1: Install Dependencies

```bash
pip install holidays  # Good Friday / Easter Monday computation
# zoneinfo is stdlib — Python 3.9+ (no install needed)
```

---

## Step 2: Configure `config.yaml`

Replace the existing `sessions:` section and add the new `filters:` section:

```yaml
sessions:
  london:
    local_open:  "08:00"
    local_close: "17:00"
    timezone:    "Europe/London"
    enabled:     true
  new_york:
    local_open:  "08:00"
    local_close: "17:00"
    timezone:    "America/New_York"
    enabled:     true

filters:
  spread:
    max_spread_usd: 0.50
  news:
    pre_event_minutes:  30
    post_event_minutes: 15
    calendar_path: "data/news_calendar.json"
    impact_levels: ["HIGH"]
  volatility:
    atr_lookback:      14
    low_atr_ratio:     0.50
    extreme_atr_ratio: 5.0

logging:
  filters_log: logs/filter_decisions.json
```

---

## Step 3: Prepare News Calendar

Create `data/news_calendar.json` with upcoming HIGH-impact events:

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
  }
]
```

---

## Step 4: Load and Evaluate Filters

```python
import yaml
from datetime import datetime, timezone
from src.filters import evaluate_filters, load_news_calendar

# Load config
with open("config.yaml") as f:
    config = yaml.safe_load(f)

# Load news calendar once at startup (caller responsibility)
news_events = load_news_calendar(config["filters"]["news"]["calendar_path"])

# At signal time — values sourced from MT5 and SMC engine
result = evaluate_filters(
    signal_id="sig_001",
    now_utc=datetime.now(timezone.utc),
    spread_usd=0.28,          # mt5.symbol_info("XAUUSD").ask - .bid
    news_events=news_events,
    current_atr=12.5,         # ATR(14) on H1 — most recent bar
    reference_atr=14.2,       # Rolling 50-bar mean of ATR(14) on H1
    config=config,
)

print(f"Final result: {result.final_result.value}")
for d in result.decisions:
    print(f"  [{d.filter_name}] {d.result.value} — {d.reason} (metric={d.metric_value})")

# If blocked, first BLOCKED decision explains why
if result.final_result.value == "BLOCKED":
    blocked = next(d for d in result.decisions if d.result.value == "BLOCKED")
    print(f"Blocked by: {blocked.filter_name} — {blocked.reason}")
```

---

## Step 5: Check Individual Filters (for debugging)

```python
from datetime import datetime, timezone
from src.filters.session_filter import check_session, get_current_session
from src.filters.spread_filter import check_spread
from src.filters.news_filter import load_news_calendar, check_news
from src.filters.volatility_filter import check_volatility

now = datetime.now(timezone.utc)

# Session filter
session = get_current_session(now, config)
print(f"Session: {session.value}")

decision = check_session(now, config)
print(f"Session filter: {decision.result.value} — {decision.reason}")

# Spread filter
decision = check_spread(0.28, config)
print(f"Spread filter: {decision.result.value} — {decision.reason}")

# News filter
events = load_news_calendar("data/news_calendar.json")
decision = check_news(now, events, config)
print(f"News filter: {decision.result.value} — {decision.reason}")

# Volatility filter
decision = check_volatility(current_atr=12.5, reference_atr=14.2, config=config)
print(f"Volatility filter: {decision.result.value} — {decision.reason}")
```

---

## Step 6: Run Tests

```bash
# Unit tests
pytest tests/unit/test_filters_session.py -v
pytest tests/unit/test_filters_spread.py -v
pytest tests/unit/test_filters_news.py -v
pytest tests/unit/test_filters_volatility.py -v
pytest tests/unit/test_filters_trade_gate.py -v

# Integration tests
pytest tests/integration/test_filters_pipeline.py -v

# Coverage report
pytest --cov=src/filters --cov-report=term-missing

# Verify no MT5 imports leaked into filter module
grep -r "MetaTrader5\|import mt5" src/filters/
# Expected: no output
```
