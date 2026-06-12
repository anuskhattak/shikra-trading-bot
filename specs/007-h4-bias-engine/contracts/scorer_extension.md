# Contract: Scorer Extension

**Module**: `src/engine/scorer.py`  
**Feature**: 007-h4-bias-engine

---

## Updated `score_and_assemble` Signature

```python
def score_and_assemble(
    signal_type: SignalType,
    fvg_zones: list[FVGZone],
    order_blocks: list[OrderBlock],
    sweeps: list[LiquiditySweep],
    weights: dict[str, float],
    threshold: float,
    htf_bias: Bias,
    htf_bias_strength: float = 0.0,    # NEW
) -> EntrySignal:
```

**Backward compatibility**: `htf_bias_strength` has a default value of `0.0`. All existing callers continue to work without modification.

---

## Scoring Logic Changes

### New weight keys (added to `weights` dict)

| Key | Default | Description |
|-----|---------|-------------|
| `h4_alignment` | `0.20` | Added to confidence when H4 bias aligns with signal direction |
| `mtf_boost` | `1.30` | Multiplier applied to confidence after h4_alignment is added |

### New processing order (inserted before existing HTF bias filter)

```
1. RANGING early-exit     → if htf_bias == RANGING: log H4_RANGING, return NONE
2. Component scoring      → bos/choch + fvg + ob + sweep (unchanged)
3. H4 alignment boost     → if aligned: confidence += h4_alignment weight
4. MTF multiplier         → if aligned: confidence *= mtf_boost (capped at 1.0)
5. HTF counter-trend exit → if BULLISH+SHORT or BEARISH+LONG: log and discard (unchanged)
6. Threshold filter       → confidence < threshold: log and discard (unchanged)
7. Entry zone assembly    → (unchanged)
8. EntrySignal return     → with h4_bias and h4_bias_strength populated
```

---

## Updated `_log_and_discard` (no signature change)

The existing `_log_and_discard` function already handles RANGING rejections because it takes an arbitrary `reason` string. The caller passes `"... [H4_RANGING]"` as the reason — no new logging function needed.

---

## EntrySignal Population

All returned `EntrySignal` objects (NONE or accepted) must populate:
- `h4_bias = htf_bias`
- `h4_bias_strength = htf_bias_strength`

This includes `_none_signal()` and `_log_and_discard()` helpers — both must be updated to accept and embed these values.
