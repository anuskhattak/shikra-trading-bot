# Quickstart: MT5 Broker Connection

**Feature**: 001-mt5-broker
**Date**: 2026-05-11

---

## Prerequisites

1. MetaTrader 5 terminal installed on Windows 10+
2. Python 3.10+ with dependencies installed
3. `.env` file created at project root

---

## Step 1: Setup .env

Create `.env` in project root (never commit this file):

```env
MT5_ACCOUNT=12345678
MT5_PASSWORD=your_broker_password
MT5_SERVER=BrokerName-Live
```

Verify `.gitignore` has `.env` entry — never commit credentials.

---

## Step 2: Install Dependencies

```powershell
pip install MetaTrader5 loguru pandas python-dotenv
```

---

## Step 3: Connect and Fetch Data

```python
from src.broker.connection import BrokerConnection
from src.broker.market_data import MarketData
from src.broker.order_manager import OrderManager, OrderType

# Load credentials from .env and connect
conn = BrokerConnection.from_env()
if not conn.connect():
    print("Connection failed — check MT5 terminal and .env")
    exit(1)

# Fetch live quote
data = MarketData(max_spread_points=30)
quote = data.get_quote()
if quote:
    print(f"XAUUSD bid={quote.bid} ask={quote.ask} spread={quote.spread_points}pts")

# Fetch historical bars for all 3 timeframes
bars = data.get_all_timeframes()
for tf, df in bars.items():
    print(f"{tf}: {len(df)} bars" if df is not None else f"{tf}: data unavailable")

# Clean disconnect
conn.disconnect()
```

---

## Step 4: Place a Paper Trade

```python
mgr = OrderManager(magic_number=202605)

order = mgr.place_order(
    order_type=OrderType.BUY,
    volume=0.01,
    stop_loss=1900.00,   # Must be below current price for BUY
    take_profit=1950.00, # Must be above current price for BUY
    comment="Shikra-test",
)

print(f"Order result: {order.result}")
print(f"Ticket: {order.broker_ticket}")
```

---

## Log Files

| File | Contents |
|---|---|
| `logs/trades.json` | All order attempts with full context |
| `logs/connection_events.json` | All connection events with timestamps |

---

## Running Tests

```powershell
# Unit tests (no MT5 terminal required)
pytest tests/unit/ -v

# Integration tests (MT5 terminal must be running)
pytest tests/integration/ -v

# Full suite
pytest -v
```

---

## Common Errors

| Error Message | Cause | Fix |
|---|---|---|
| `Terminal Unavailable` | MT5 terminal not running | Start MT5 terminal manually |
| `Authentication Failed` | Wrong credentials in `.env` | Check account/password/server |
| `Missing SL/TP — Order Rejected` | SL or TP is 0 or wrong side | Recalculate SL/TP from risk manager |
| `High Spread — Trade Skipped` | Spread > `max_spread_points` | Wait for tighter spread or increase threshold |
| `Insufficient Margin` | Account balance too low | Check account balance with broker |
