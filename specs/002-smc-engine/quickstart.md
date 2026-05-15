# Quickstart: SMC Signal Detection Engine

**Feature**: 002-smc-engine
**Date**: 2026-05-12

---

## Prerequisites

- `001-mt5-broker` feature complete and tested
- MT5 terminal running (for live data) OR synthetic DataFrame (for testing)
- `config.yaml` at project root with `smc_engine:` section

---

## Step 1 — Install dependencies

```bash
pip install -r requirements.txt
# Required: pandas>=2.0, numpy>=1.24, loguru, pyyaml
```

---

## Step 2 — Configure weights (config.yaml)

```yaml
smc_engine:
  fractal_n: 2
  lookback_window: 20
  equal_level_tolerance_pips: 5
  confidence_threshold: 0.65
  weights:
    bos_or_choch: 0.40
    fvg: 0.30
    order_block: 0.20
    liquidity_sweep: 0.10
  min_candles: 50
```

---

## Step 3 — Use with live MT5 data

```python
from src.broker.connection import BrokerConnection
from src.broker.market_data import MarketData, Timeframe
from src.engine.smc_engine import generate_signal
from src.engine.models import Bias

# Connect and get data (001-mt5-broker)
conn = BrokerConnection.from_env()
conn.connect()
data = MarketData(conn)

df_h1 = data.get_ohlcv(Timeframe.H1, count=200)

# Generate signal (no MT5 needed beyond the DataFrame)
signal = generate_signal(df_h1, htf_bias=Bias.BULLISH)

print(f"Direction : {signal.direction}")
print(f"Confidence: {signal.confidence:.2f}")
print(f"Entry zone: {signal.entry_zone_bottom:.2f} – {signal.entry_zone_top:.2f}")
print(f"Reason    : {signal.reason}")
```

---

## Step 4 — Use with synthetic data (testing / backtesting)

```python
import pandas as pd
import numpy as np
from src.engine.smc_engine import generate_signal
from src.engine.models import Bias, Direction

# Build minimal synthetic DataFrame
dates = pd.date_range("2026-01-01", periods=100, freq="1h")
df = pd.DataFrame({
    "time": dates,
    "open":  np.random.uniform(2300, 2400, 100),
    "high":  np.random.uniform(2300, 2400, 100),
    "low":   np.random.uniform(2300, 2400, 100),
    "close": np.random.uniform(2300, 2400, 100),
    "tick_volume": np.random.randint(100, 1000, 100),
})

signal = generate_signal(df, htf_bias=Bias.NEUTRAL)
assert signal is not None            # never None
assert 0.0 <= signal.confidence <= 1.0
```

---

## Step 5 — Check false_signals.json

Discarded signals are automatically logged:

```bash
cat logs/false_signals.json
# [
#   {"timestamp": "2026-05-12T14:30:00", "confidence": 0.40, "reason": "Below confidence threshold"},
#   ...
# ]
```

---

## Expected output for a high-confluence setup

```
Direction : LONG
Confidence: 0.90
Entry zone: 2348.50 – 2352.00
Reason    : BOS_BULLISH + FVG + OB
```

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `signal.direction == NONE` always | Fewer than 50 candles | Pass at least 50 rows |
| `confidence` always 0.40 | Only BOS firing; no FVG/OB alignment | Check candle data quality |
| `false_signals.json` growing large | Low-confluence market | Normal — reduce lookback or adjust weights |
| `KeyError: smc_engine` | config.yaml missing section | Add `smc_engine:` block per Step 2 |
