# Contract: Shared Pipeline Core

**Module**: `src/orchestrator/pipeline.py`  
**Purpose**: Single function that runs the full SMC signal → filter → risk pipeline. Used identically by live orchestrator and backtest engine.

---

## `run_pipeline`

```python
def run_pipeline(
    ctx: PipelineContext,
    atr_service: ATRService,
    config: dict,
) -> PipelineContext:
    """Run the full pipeline for one bar evaluation.

    Stages:
      1. ATR Refresh — update ATRService cache for all timeframes in ctx.bars
      2. SMC Signal Detection — detect BOS/CHoCH/FVG/OB/LS, score, assemble EntrySignal
      3. Filter Gate — run evaluate_filters(); short-circuit if BLOCKED
      4. Risk Calculation — compute SL/TP/lot size (only if filter passed)

    Args:
        ctx: PipelineContext with bars, now_utc, spread_usd, news_events, mode pre-filled.
        atr_service: Shared ATRService instance (same instance used by caller).
        config: Full config dict (all module sections accessible).

    Returns:
        Same ctx object with atr_readings, entry_signal, filter_result, risk_calc populated.
        Unreached fields remain None (e.g., risk_calc is None if filter blocked).

    Never raises. All exceptions caught internally; ctx.entry_signal set to NONE on failure.
    """
```

### Short-circuit rules:
1. If `ATRService.is_ready(Timeframe.H1)` is False → `entry_signal.direction = NONE`, return immediately (no filter/risk)
2. If `entry_signal.direction == NONE` (no SMC pattern) → return immediately (no filter/risk)
3. If `filter_result.final_result == BLOCKED` → return immediately (no risk calc)

### Error handling:
- Any exception in Stage 1 (ATR): log WARNING, leave `atr_readings` empty, return ctx with `entry_signal=None`
- Any exception in Stage 2 (SMC): log ERROR, set `entry_signal` to NONE signal, continue to filter
- Any exception in Stage 3 (filters): log ERROR, set `filter_result.final_result = BLOCKED`, return
- Any exception in Stage 4 (risk): log ERROR, leave `risk_calc = None`, return

---

## `PipelineContext` (dataclass)

```python
@dataclass
class PipelineContext:
    # Inputs (set by caller before run_pipeline)
    signal_id: str
    timeframe: Timeframe                       # Primary signal timeframe (always H1)
    bars: dict[Timeframe, list[OHLCVBar]]      # Keyed by Timeframe; H1 always present
    now_utc: datetime
    spread_usd: float
    news_events: list[NewsEvent]               # [] in backtest mode
    mode: str                                  # "live" | "backtest"

    # Outputs (populated by run_pipeline)
    atr_readings: dict[Timeframe, ATRReading] = field(default_factory=dict)
    entry_signal: Optional[EntrySignal] = None
    filter_result: Optional[TradeGateResult] = None
    risk_calc: Optional[RiskCalculation] = None
```

---

## `bar_monitor.poll_for_new_bar`

```python
def poll_for_new_bar(
    last_bar_time: Optional[datetime],
    symbol: str = "XAUUSD",
    timeframe_mt5: int = mt5.TIMEFRAME_H1,
    fetch_count: int = 150,
) -> tuple[bool, datetime, dict[Timeframe, list[OHLCVBar]]]:
    """Poll MT5 for a new bar close.

    Args:
        last_bar_time: UTC timestamp of the most recently processed bar. None on first call.
        symbol: MT5 symbol name.
        timeframe_mt5: MT5 timeframe constant (default: H1).
        fetch_count: Number of bars to fetch when new bar detected (default: 150).

    Returns:
        (is_new_bar, current_bar_time, bars_dict)
        - is_new_bar: True if current_bar_time != last_bar_time (new bar detected)
        - current_bar_time: Timestamp of the most recent bar from MT5
        - bars_dict: dict[Timeframe, list[OHLCVBar]] — only populated when is_new_bar=True;
                     contains 150 bars for all 4 timeframes

    Raises:
        MT5ConnectionError: if mt5.copy_rates_from_pos() returns None (terminal disconnected)
    """
```
