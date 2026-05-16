# Module Contract: Risk Management

**Feature**: 003-risk-management
**Created**: 2026-05-16

---

## Public Interface

### `src/risk/risk_manager.py`

```python
def evaluate_trade_risk(
    entry_signal:   EntrySignal,    # from src.engine.models
    balance:        float,          # current account balance (USD)
    current_equity: float,          # current account equity (USD)
    d1_atr:         float,          # D1 ATR(14) in price units (e.g. 18.50)
    state:          RiskState,      # session state — never mutate in place; return new instance
    config:         dict | None,    # risk: section from config.yaml, or None for defaults
) -> tuple[RiskCalculation, RiskState]:
    """Main entry point. Returns (RiskCalculation, updated_state).

    Returns zero_risk_calc (lot=0.0, SL/TP=0.0) when:
    - entry_signal.direction == Direction.NONE
    - drawdown limit reached
    - trade limits reached
    - signal rejected in recovery mode
    Never raises on valid inputs.
    On allowed=True: appends DEBUG entry to logs/risk_events.json (NFR-006); silent fail.
    """
```

---

### `src/risk/lot_calculator.py`

```python
XAUUSD_PIP_VALUE: float = 10.0  # $10 per pip per standard lot — MT5 contract spec

def calculate_lot_size(
    balance:            float,
    risk_percent:       float,   # e.g. 1.0 for 1%
    sl_distance:        float,   # stop loss distance in price units (same unit as D1_ATR)
    pip_value_per_lot:  float = XAUUSD_PIP_VALUE,
    max_lot:            float = 5.0,
    min_lot:            float = 0.01,
) -> float:
    """Returns lot size rounded to 2 decimal places, clamped to [min_lot, max_lot].
    5% balance hard cap applied before clamping (D-007).
    """

def calculate_sl_price(
    entry:             float,
    direction:         Direction,  # Direction.LONG or Direction.SHORT
    d1_atr:            float,
    sl_atr_multiplier: float = 1.5,
) -> float:
    """Returns SL price. For LONG: entry - (d1_atr * multiplier). For SHORT: entry + (...)."""

def _calculate_sl_distance(d1_atr: float, sl_atr_multiplier: float) -> float:
    """Private helper. Returns sl_distance in price units = d1_atr * sl_atr_multiplier."""

def calculate_tp_prices(
    entry:     float,
    sl_price:  float,
    direction: Direction,
    tp1_rr:    float = 1.5,
    tp2_rr:    float = 3.0,
) -> tuple[float, float]:
    """Returns (tp1_price, tp2_price). Invariant: LONG → entry < tp1 < tp2."""
```

---

### `src/risk/drawdown_guard.py`

```python
def check_drawdown(
    day_start_equity: float,
    current_equity:   float,
    max_pct:          float,  # e.g. 5.0 for 5%
) -> TradeAllowedResult:
    """Returns TradeAllowedResult(allowed=False, reason=...) when drawdown >= max_pct."""

def reset_daily_state(state: RiskState, current_equity: float) -> RiskState:
    """Returns new RiskState with day_start_equity=current_equity, trades_today=0,
    session_trades reset. Call this at broker midnight (00:00)."""

def get_drawdown_pct(day_start_equity: float, current_equity: float) -> float:
    """Returns drawdown as a positive percentage. Returns 0.0 if equity >= start."""
```

---

### `src/risk/trade_limits.py`

```python
def is_trade_limit_allowed(
    state:        RiskState,
    config:       dict,
    current_time: datetime,
    session:      str,        # e.g. "LONDON", "NEW_YORK", "OVERLAP"
) -> TradeAllowedResult:
    """Checks daily limit, session limit, and SL cooldown. Returns first block found."""

def record_trade_opened(state: RiskState, session: str) -> RiskState:
    """Returns new RiskState with trades_today+1 and session_trades[session]+1."""

def record_sl_hit(state: RiskState, current_time: datetime) -> RiskState:
    """Returns new RiskState with last_sl_time=now, consecutive_losses+1."""

def record_trade_won(state: RiskState) -> RiskState:
    """Returns new RiskState with consecutive_losses=0."""
```

---

### `src/risk/recovery_mode.py`

```python
def check_recovery_status(state: RiskState, config: dict) -> RiskState:
    """Returns new RiskState with in_recovery_mode=True if consecutive_losses >= threshold.
    Logs entry/exit events to logs/risk_events.json."""

def is_signal_allowed_in_recovery(
    confidence:             float,
    recovery_min_confidence: float,
) -> bool:
    """Returns False when confidence < recovery_min_confidence during recovery mode."""

def apply_recovery_lot(lot_size: float, recovery_lot_multiplier: float) -> float:
    """Returns lot_size * recovery_lot_multiplier (before final clamping)."""

def update_recovery_profit(state: RiskState, pips_gained_price_units: float) -> RiskState:
    """Adds pips_gained_price_units to state.recovery_profit_pips. Exits recovery if target reached.
    Called by spec004 (Execution Engine) after each closed trade (FR-028)."""
```

---

## Invariants

| Invariant | Description |
|-----------|-------------|
| `lot_size >= 0.01` | MT5 minimum, always enforced |
| `lot_size <= max_lot_size` | Hard cap, always enforced |
| `risk_amount <= balance * 0.05` | 5% hard cap, applied before clamping |
| LONG: `sl_price < entry_price < tp1_price < tp2_price` | Price ordering |
| SHORT: `tp2_price < tp1_price < entry_price < sl_price` | Price ordering |
| `evaluate_trade_risk` never raises | Returns zero_risk_calc on any error |
| No MT5 import in any `src/risk/` file | NFR-001 |

---

## Zero Risk Calculation (blocked trade)

When trading is blocked for any reason:

```python
RiskCalculation(
    lot_size=0.0,
    sl_price=0.0,
    tp1_price=0.0,
    tp2_price=0.0,
    sl_distance=0.0,
    risk_amount_usd=0.0,
    in_recovery=state.in_recovery_mode,
    reason="<block reason>",
)
```

The caller (spec004) checks `lot_size == 0.0` to skip trade execution.
