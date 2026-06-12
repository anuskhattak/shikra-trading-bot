# Quickstart: H4 Bias Engine

**Feature**: 007-h4-bias-engine  
**Date**: 2026-06-12

---

## What Was Built

`H4BiasService` — a stateful H4 directional bias detector that classifies XAUUSD H4 market structure as BULLISH, BEARISH, or RANGING using fractal swing-point sequences.

---

## New Files

| File | Purpose |
|------|---------|
| `src/analysis/h4_bias.py` | H4BiasService class, H4BiasResult dataclass, classify_bias() |
| `tests/test_h4_bias.py` | 9 unit tests |

## Modified Files

| File | Change |
|------|--------|
| `src/engine/models.py` | Added `Bias.RANGING`; added `h4_bias`, `h4_bias_strength` to `EntrySignal` |
| `src/engine/scorer.py` | RANGING block; h4_alignment boost; MTF multiplier; EntrySignal embedding |
| `src/engine/smc_engine.py` | Thread `htf_bias_strength` through `generate_signal()` |
| `src/orchestrator/pipeline.py` | Stage 0 H4 bias refresh; `h4_bias_service` parameter |
| `src/orchestrator/models.py` | Added `h4_bias_result` to `PipelineContext` |

---

## Config Required

Add to `config.yaml`:

```yaml
analysis:
  h4_bias:
    lookback_bars: 20
    fractal_n: 2
    bullish_strength_threshold: 0.60
    bearish_strength_threshold: 0.60

smc_engine:
  weights:
    bos_or_choch:    0.40
    fvg:             0.30
    order_block:     0.20
    liquidity_sweep: 0.10
    h4_alignment:    0.20
    mtf_boost:       1.30
```

---

## Integration (pipeline caller)

```python
from src.analysis.h4_bias import H4BiasService
from src.analysis.atr_service import ATRService

# Instantiate once at bot startup
atr_service = ATRService(config)
h4_bias_service = H4BiasService(config)

# Call on each H4 bar event
result = run_pipeline(ctx, atr_service, h4_bias_service, config)
```

---

## How Bias Affects Signal Scoring

| H4 Bias | H1 Signal | Effect |
|---------|-----------|--------|
| RANGING | Any | Blocked → `H4_RANGING` logged, NONE signal returned |
| BULLISH | LONG | +0.20 confidence boost + ×1.30 MTF multiplier |
| BEARISH | SHORT | +0.20 confidence boost + ×1.30 MTF multiplier |
| BULLISH | SHORT | Counter-trend → discarded (existing behavior) |
| BEARISH | LONG | Counter-trend → discarded (existing behavior) |
| NEUTRAL | Any | No boost, no block (default until H4BiasService is warmed up) |

---

## LSTM Replacement (spec012)

To swap the ATR-based engine for the LSTM predictor, implement `LSTMBiasService` with the same interface:

```python
class LSTMBiasService:
    def refresh(self, h4_bars: list[OHLCVBar]) -> H4BiasResult: ...
    def get_bias(self) -> H4BiasResult: ...
    def is_ready(self) -> bool: ...
```

Then replace `H4BiasService(config)` with `LSTMBiasService(config)` at the instantiation site. No changes to `pipeline.py`, `scorer.py`, or `smc_engine.py`.

---

## Running Tests

```bash
pytest tests/test_h4_bias.py -v
```
