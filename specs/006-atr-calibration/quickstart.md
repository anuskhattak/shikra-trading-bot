# Quickstart: ATR Calibration Module

**Feature**: 006-atr-calibration  
**Date**: 2026-05-22

---

## Usage

### 1. Initialise ATRService

```python
from src.analysis import ATRService, Timeframe, VolatilityRegime

with open("config.yaml") as f:
    config = yaml.safe_load(f)

atr_service = ATRService(config)
```

### 2. Refresh on each bar close (called by orchestrator)

```python
# On new H1 bar close:
h1_bars = market_data.get_ohlcv("XAUUSD", Timeframe.H1.value, count=50)
atr_service.refresh(Timeframe.H1, h1_bars)

# On new D1 bar close:
d1_bars = market_data.get_ohlcv("XAUUSD", Timeframe.D1.value, count=50)
atr_service.refresh(Timeframe.D1, d1_bars)
```

### 3. Feed volatility filter (spec004)

```python
from src.filters.volatility_filter import check_volatility

current_atr, reference_atr = atr_service.get_h1_readings()
if current_atr and reference_atr:
    decision = check_volatility(current_atr, reference_atr, config)
```

### 4. Feed lot calculator (spec003)

```python
from src.risk.lot_calculator import calculate_sl_price, calculate_lot_size

d1_atr = atr_service.get_d1_atr()
if d1_atr:
    # Get adaptive multiplier based on current regime
    regime = VolatilityRegime.NORMAL  # from volatility filter result
    multipliers = atr_service.get_adaptive_multipliers(regime)

    sl_price = calculate_sl_price(
        entry=entry_price,
        direction=direction,
        d1_atr=d1_atr,
        sl_atr_multiplier=multipliers.sl_multiplier,
    )
```

### 5. Check readiness before use

```python
if not atr_service.is_ready(Timeframe.D1):
    logger.warning("D1 ATR not yet available — skipping trade")
    return
```

---

## Config (`config.yaml`)

```yaml
analysis:
  atr:
    period: 14              # True Range lookback (Wilder's standard)
    reference_period: 20    # Rolling ATR average window
    adaptive_multipliers:
      sl:
        LOW: 1.0
        NORMAL: 1.5
        EXTREME: 2.0
      tp:
        LOW: 2.0
        NORMAL: 3.0
        EXTREME: 4.0

filters:
  volatility:
    low_atr_ratio: 0.7      # Existing — unchanged
    extreme_atr_ratio: 2.0  # Existing — unchanged
```

---

## Run Tests

```bash
# Unit tests only (no MT5 required)
pytest tests/unit/test_atr_calculator.py -v
pytest tests/unit/test_reference_atr.py -v
pytest tests/unit/test_adaptive_multipliers.py -v
pytest tests/unit/test_atr_service.py -v

# All analysis unit tests
pytest tests/unit/ -k "atr" -v

# Coverage check
pytest tests/unit/ -k "atr" --cov=src/analysis --cov-report=term-missing
```

---

## File Layout

```text
src/analysis/
├── __init__.py
├── models.py                — Timeframe, OHLCVBar, VolatilityRegime,
│                              AdaptiveMultipliers, ATRReading, ATRCache
├── atr_calculator.py        — validate_ohlcv_bars(), compute_true_range(), compute_atr()
├── reference_atr.py         — compute_reference_atr()
├── adaptive_multipliers.py  — get_adaptive_multipliers()
└── atr_service.py           — ATRService (stateful cache + orchestration)

tests/unit/
├── test_atr_models.py
├── test_atr_calculator.py
├── test_reference_atr.py
├── test_adaptive_multipliers.py
└── test_atr_service.py
```
