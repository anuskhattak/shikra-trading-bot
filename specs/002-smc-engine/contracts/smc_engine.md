# Contract: SMC Signal Detection Engine

**Feature**: 002-smc-engine
**Date**: 2026-05-12
**Type**: Python public interface contract (function signatures + type annotations)

---

## Public Interface — `src/engine/smc_engine.py`

### Primary Entry Point

```python
def generate_signal(
    df: pd.DataFrame,
    htf_bias: Bias = Bias.NEUTRAL,
    config: dict | None = None,
) -> EntrySignal:
    """
    Analyse XAUUSD H1 OHLCV candles and return a scored SMC entry signal.

    Args:
        df:        H1 OHLCV DataFrame with columns [time, open, high, low, close, tick_volume].
                   Minimum 50 rows required; returns NONE signal if fewer bars provided.
        htf_bias:  Pre-computed higher-timeframe directional bias. Engine filters signals
                   to match this direction. NEUTRAL = no filter (any direction accepted).
        config:    Optional config dict overriding config.yaml defaults. Keys match
                   config.yaml schema. Pass None to use project defaults.

    Returns:
        EntrySignal — always returns a valid object, never None or raises.
        EntrySignal.direction == NONE when no valid setup found or confidence below threshold.

    Guarantees:
        - Stateless: does not mutate df or retain state between calls (NFR-002)
        - Deterministic: identical df + config always produces identical EntrySignal (SC-006)
        - No MT5 import: operates purely on pandas DataFrames (NFR-003)
        - Performance: < 100ms for 200-row df (SC-005)
    """
```

---

## Internal Module Contracts

### `src/engine/swing.py`

```python
def detect_swing_points(
    df: pd.DataFrame,
    fractal_n: int = 2,
    lookback: int = 20,
) -> list[SwingPoint]:
    """
    Identify confirmed swing highs and lows using fractal rule.
    Returns only confirmed pivots (both sides have fractal_n candles satisfying condition).
    Last fractal_n rows are always unconfirmed and excluded from output.
    """
```

### `src/engine/bos_choch.py`

```python
def detect_structure_break(
    df: pd.DataFrame,
    swing_points: list[SwingPoint],
) -> tuple[SignalType, float | None]:
    """
    Detect BOS or CHoCH from confirmed swing points.
    Returns (SignalType, broken_level_price) or (SignalType.NONE, None).
    Uses candle CLOSE only — wick moves never trigger BOS/CHoCH (FR-004).
    """
```

### `src/engine/fvg.py`

```python
def detect_fvg_zones(
    df: pd.DataFrame,
    direction_filter: Direction = Direction.NONE,
) -> list[FVGZone]:
    """
    Scan all candles for Fair Value Gaps. Returns list ordered newest-first.
    Applies fill check: zones where a subsequent candle closed inside are marked FILLED.
    direction_filter: when set, returns only zones matching that direction.
    """
```

### `src/engine/order_block.py`

```python
def detect_order_blocks(
    df: pd.DataFrame,
    bos_type: SignalType,
    bos_candle_index: int,
) -> list[OrderBlock]:
    """
    Identify Order Blocks — last opposing candle before the BOS.
    Updates OB status (ACTIVE / TESTED / INVALIDATED) by scanning subsequent candles.
    Returns list of OBs; most recent first.
    bos_type and bos_candle_index must come from detect_structure_break output.
    """
```

### `src/engine/liquidity_sweep.py`

```python
def detect_liquidity_sweeps(
    df: pd.DataFrame,
    pip_tolerance: float = 0.50,
) -> list[LiquiditySweep]:
    """
    Identify Liquidity Sweep events.
    Equal levels: two or more candle highs/lows within pip_tolerance.
    Sweep: candle wicks beyond equal level and closes back inside — same candle.
    Returns detected sweeps, newest first.
    """
```

### `src/engine/scorer.py`

```python
def score_and_assemble(
    signal_type: SignalType,
    fvg_zones: list[FVGZone],
    order_blocks: list[OrderBlock],
    sweeps: list[LiquiditySweep],
    weights: dict[str, float],
    threshold: float,
    htf_bias: Bias,
) -> EntrySignal:
    """
    Combine detected components into a scored EntrySignal.
    Logs discarded signals to logs/false_signals.json (FR-023).
    entry_zone: OB body when active OB present; FVG boundaries as fallback (FR-017).
    Always returns a valid EntrySignal — never raises.
    """
```

---

## Guaranteed Invariants (all functions)

| Invariant | Enforced By |
|-----------|-------------|
| Never returns None | Return type is always a typed object or list |
| Never raises on valid DataFrame input | try/except in generate_signal wraps all sub-calls |
| Never imports MetaTrader5 | NFR-003 — enforced at module level |
| Confidence in [0.0, 1.0] | scorer.py clips to range after sum |
| Weights sum == 1.0 | config loader asserts at startup |
| NONE signal has entry_zone = (0.0, 0.0) | scorer.py sets explicitly |

---

## DataFrame Input Contract

```
Required columns: time, open, high, low, close, tick_volume
Column types:     time (datetime64), open/high/low/close (float64), tick_volume (int64)
Minimum rows:     50 (returns NONE signal if fewer)
Row order:        Ascending by time (oldest first, newest last)
No NaN allowed:   In open, high, low, close columns
```

**Provided by**: `MarketData.get_ohlcv(Timeframe.H1)` from `001-mt5-broker` feature.
