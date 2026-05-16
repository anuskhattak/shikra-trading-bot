# Data Model: Risk Management Module

**Feature**: 003-risk-management
**Created**: 2026-05-16

---

## Enums

```python
from enum import Enum

class RecoveryReason(Enum):
    CONSECUTIVE_LOSSES = "consecutive_losses"  # N SL hits in a row
    # Future: BASKET_DRAWDOWN = "basket_drawdown"

class BlockReason(Enum):
    DRAWDOWN_LIMIT     = "daily_drawdown_limit"
    DAILY_TRADE_LIMIT  = "daily_trade_limit"
    SESSION_TRADE_LIMIT = "session_trade_limit"
    COOLDOWN_ACTIVE    = "cooldown_active_after_sl"
    NOT_BLOCKED        = "not_blocked"
```

---

## Dataclasses

### `RiskCalculation` — Output of the risk module

```python
@dataclass
class RiskCalculation:
    lot_size:        float          # Calculated and clamped lot size
    sl_price:        float          # Stop loss price level
    tp1_price:       float          # Take profit 1 price level
    tp2_price:       float          # Take profit 2 price level
    sl_distance:      float          # SL distance in price units (for audit); e.g. 30.0 = $30 move
    risk_amount_usd: float          # Dollar risk for this trade
    in_recovery:     bool           # Whether recovery mode was active
    reason:          str            # Human-readable summary

    # Invariants:
    # LONG:  sl_price < entry_price < tp1_price < tp2_price
    # SHORT: tp2_price < tp1_price < entry_price < sl_price
    # lot_size in [0.01, max_lot_size]
    # risk_amount_usd <= balance * 0.05
```

### `RiskState` — Session state (owned by caller, never global; functions return new instances)

```python
@dataclass
class RiskState:
    day_start_equity:    float          # Equity at broker midnight reset
    trades_today:        int            # Entries opened today
    session_trades:      dict[str, int] # {"LONDON": 1, "NEW_YORK": 0, ...}
    last_sl_time:        datetime | None  # When last SL was hit
    consecutive_losses:  int            # Current consecutive SL hits
    in_recovery_mode:    bool           # Recovery circuit breaker active
    recovery_profit_pips: float         # Pips gained since recovery started
```

### `TradeAllowedResult` — Returned by `check_drawdown()` and `is_trade_limit_allowed()`

```python
@dataclass
class TradeAllowedResult:
    allowed: bool
    reason:  str    # e.g. "Daily drawdown limit reached (6.0% >= 5.0%)"
                    #       "not_blocked" when allowed=True
```

---

## Config Schema (`config.yaml` → `risk:` section)

```yaml
risk:
  # Lot sizing
  risk_percent: 1.0          # % of balance risked per trade
  max_lot_size: 5.0          # Hard max lot cap
  min_lot_size: 0.01         # MT5 minimum (XAUUSD)
  pip_value_per_lot: 10.0    # XAUUSD: $10 per pip per standard lot

  # SL / TP
  sl_atr_multiplier: 1.5     # SL = D1_ATR * this
  tp1_rr_ratio: 1.5          # TP1 = SL_distance * this
  tp2_rr_ratio: 3.0          # TP2 = SL_distance * this

  # Drawdown guard
  max_daily_drawdown: 5.0    # % — blocks trading when hit

  # Trade limits
  max_trades_per_day: 5
  max_trades_per_session: 2
  cooldown_after_sl_hours: 2.0

  # Recovery mode
  max_consecutive_losses: 3
  recovery_lot_multiplier: 0.5
  recovery_min_confidence: 0.80
  recovery_profit_target_pips: 50.0
```

---

## Key Entities (Caller's Responsibility)

The risk module does **not** fetch these — they are passed in as parameters:

| Parameter | Source | Unit |
|-----------|--------|------|
| `balance` | `mt5.account_info().balance` | USD |
| `current_equity` | `mt5.account_info().equity` | USD |
| `d1_atr` | ATR(14) on D1 OHLCV | Price units (e.g. 18.50) |
| `entry_price` | `EntrySignal.entry_zone_top/bottom` | Price |
| `signal_confidence` | `EntrySignal.confidence` | 0.0–1.0 |

---

## Log Entry Format (`logs/risk_events.json`)

Each entry is a JSON object appended as a new line:

Blocking events (NFR-005):
```json
{
  "timestamp": "2026-05-16T10:30:00",
  "event": "drawdown_blocked | recovery_entered | recovery_exited | sl_hit",
  "detail": "Daily drawdown 6.0% >= limit 5.0%",
  "state_snapshot": {
    "trades_today": 2,
    "consecutive_losses": 3,
    "in_recovery_mode": true,
    "day_start_equity": 10000.0,
    "current_equity": 9400.0
  }
}
```

Successful evaluation (NFR-006, DEBUG level):
```json
{
  "timestamp": "2026-05-16T10:30:00",
  "event": "allowed",
  "lot_size": 0.05,
  "sl_price": 2320.0,
  "tp1_price": 2395.0,
  "tp2_price": 2440.0,
  "max_loss_usd": 100.0,
  "reason": "ALLOWED"
}
```

---

## XAUUSD Pip Value Reference

```
Symbol:        XAUUSD
Contract size: 100 oz (1 standard lot)
Tick size:     0.01 (1 pip = $0.10 for 0.01 lot)
Pip value:     $10.00 per pip per standard lot

Formula:
  pip_value_per_lot = 10.0   # constant for XAUUSD standard lots
  risk_amount = balance * (risk_percent / 100)
  lot_size = risk_amount / (sl_distance * pip_value_per_lot)
```
