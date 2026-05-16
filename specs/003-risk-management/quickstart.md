# Quickstart: Risk Management Module

**Feature**: 003-risk-management
**Created**: 2026-05-16

---

## Step 1: Install & Configure

Make sure `config.yaml` has the `risk:` section (added in T002):

```yaml
risk:
  risk_percent: 1.0
  max_lot_size: 5.0
  sl_atr_multiplier: 1.5
  tp1_rr_ratio: 1.5
  tp2_rr_ratio: 3.0
  max_daily_drawdown: 5.0
  max_trades_per_day: 5
  max_trades_per_session: 2
  cooldown_after_sl_hours: 2.0
  max_consecutive_losses: 3
  recovery_lot_multiplier: 0.5
  recovery_min_confidence: 0.80
  recovery_profit_target_pips: 50.0
```

---

## Step 2: Initialize Session State

```python
from src.risk.models import RiskState
from datetime import datetime

# At start of each trading session, initialize state
state = RiskState(
    day_start_equity=10000.0,   # from mt5.account_info().equity at midnight
    trades_today=0,
    session_trades={"LONDON": 0, "NEW_YORK": 0, "OVERLAP": 0},
    last_sl_time=None,
    consecutive_losses=0,
    in_recovery_mode=False,
    recovery_profit_pips=0.0,
)
```

---

## Step 3: Evaluate Risk for an Entry Signal

```python
import yaml
from src.risk import evaluate_trade_risk
from src.engine.models import EntrySignal, Direction, Bias

# Load config
with open("config.yaml") as f:
    full_config = yaml.safe_load(f)
config = full_config.get("risk", {})

# Example EntrySignal from SMC engine
entry_signal = EntrySignal(
    direction=Direction.LONG,
    signal_type=...,
    confidence=0.90,
    entry_zone_top=2352.0,
    entry_zone_bottom=2348.0,
    reason="BOS_BULLISH + FVG + OB",
    components=["bos", "fvg", "ob"],
    htf_bias=Bias.BULLISH,
)

# Account info (from MT5 in production)
balance = 10000.0
current_equity = 9900.0
d1_atr = 18.5  # ATR(14) on D1 timeframe

# Evaluate
risk_calc, updated_state = evaluate_trade_risk(
    entry_signal=entry_signal,
    balance=balance,
    current_equity=current_equity,
    d1_atr=d1_atr,
    state=state,
    config=config,
)

print(f"Lot size:  {risk_calc.lot_size}")
print(f"SL price:  {risk_calc.sl_price}")
print(f"TP1 price: {risk_calc.tp1_price}")
print(f"TP2 price: {risk_calc.tp2_price}")
print(f"Risk USD:  ${risk_calc.risk_amount_usd:.2f}")
print(f"Reason:    {risk_calc.reason}")

# If lot_size == 0.0, trading was blocked — check reason
if risk_calc.lot_size == 0.0:
    print(f"Trade blocked: {risk_calc.reason}")
```

---

## Step 4: Record Trade Results

```python
from src.risk import record_trade_opened, record_sl_hit, record_trade_won
from datetime import datetime

# After entry order placed
state = record_trade_opened(updated_state, session="LONDON")

# If stop loss hit
state = record_sl_hit(state, current_time=datetime.utcnow())

# If trade won (closed at TP)
state = record_trade_won(state)
```

---

## Step 5: Daily Reset (at midnight)

```python
from src.risk import reset_daily_state

# Call once per day at broker midnight (00:00 server time)
current_equity = 10150.0  # from mt5.account_info().equity
state = reset_daily_state(state, current_equity)
```

---

## Step 6: Run Tests

```bash
# Unit tests
pytest tests/unit/test_risk_lot_calculator.py -v
pytest tests/unit/test_risk_drawdown_guard.py -v
pytest tests/unit/test_risk_trade_limits.py -v
pytest tests/unit/test_risk_recovery_mode.py -v

# Integration tests
pytest tests/integration/test_risk_pipeline.py -v

# Coverage
pytest --cov=src/risk --cov-report=term-missing

# No MT5 imports check
grep -r "MetaTrader5\|import mt5" src/risk/
# Expected: no output
```
