# Contract: H4BiasService

**Module**: `src/analysis/h4_bias.py`  
**Feature**: 007-h4-bias-engine

---

## H4BiasResult

```python
@dataclass(frozen=True)
class H4BiasResult:
    bias:        Bias     # BULLISH | BEARISH | RANGING
    strength:    float    # 0.0–1.0 conviction
    swing_count: int      # confirmed fractal swings used (0 on cold start)
    timestamp:   datetime
```

---

## H4BiasService

```python
class H4BiasService:
    def __init__(self, config: dict) -> None:
        """
        Reads config['analysis']['h4_bias']:
          lookback_bars: int = 20
          fractal_n:     int = 2
          bullish_strength_threshold: float = 0.60
          bearish_strength_threshold: float = 0.60

        Raises KeyError if config['analysis']['h4_bias'] section missing.
        """

    def refresh(self, h4_bars: list[OHLCVBar]) -> H4BiasResult:
        """
        Compute H4 directional bias from pre-fetched H4 OHLCV bars.

        Calls detect_swing_points() → classify_bias() → stores result in cache.
        Never raises. On any error: returns RANGING / 0.0 and logs WARNING.

        Cold start (len(h4_bars) < lookback_bars):
            Returns H4BiasResult(bias=Bias.RANGING, strength=0.0, swing_count=0, ...)
        """

    def get_bias(self) -> H4BiasResult:
        """
        Return last cached H4BiasResult.
        Before first successful refresh(): returns RANGING / 0.0 result.
        """

    def is_ready(self) -> bool:
        """
        True after at least one successful refresh() with enough bars.
        """
```

---

## classify_bias (module-level helper)

```python
def classify_bias(
    swing_points: list[SwingPoint],
    bullish_threshold: float = 0.60,
    bearish_threshold: float = 0.60,
) -> tuple[Bias, float]:
    """
    Classify market direction from a sequence of fractal swing points.

    Algorithm:
    1. Separate swings into HIGHS and LOWS lists (by SwingPoint.type).
    2. For consecutive HIGH pairs: count HH (each > prior) for bullish, LH for bearish.
    3. For consecutive LOW pairs:  count HL (each > prior) for bullish, LL for bearish.
    4. bullish_score = (HH_count + HL_count) / (total_high_pairs + total_low_pairs)
    5. bearish_score = (LH_count + LL_count) / (total_high_pairs + total_low_pairs)
    6. If bullish_score >= bullish_threshold → (BULLISH, bullish_score)
       If bearish_score >= bearish_threshold → (BEARISH, bearish_score)
       Else                                  → (RANGING, max(bullish_score, bearish_score))

    Returns (RANGING, 0.0) when swing_points is empty or has fewer than 2 of same type.
    Never raises.
    """
```

---

## LSTM Replaceability Contract

In spec012, `LSTMBiasService` must implement:

```python
class LSTMBiasService:
    def refresh(self, h4_bars: list[OHLCVBar]) -> H4BiasResult: ...
    def get_bias(self) -> H4BiasResult: ...
    def is_ready(self) -> bool: ...
```

The pipeline accesses `h4_bias_service.refresh(h4_bars)` and `h4_bias_service.get_bias()` only — no other attributes. The `H4BiasResult` return type is shared; `LSTMBiasService` populates `bias` from softmax prediction and `strength` from max class probability.
