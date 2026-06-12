# Research: ATR Calibration Module

**Feature**: 006-atr-calibration  
**Date**: 2026-05-22  
**Purpose**: Resolve all design decisions before implementation

---

## D-001: ATR Calculation Method — Simple Average vs Wilder's EMA

**Decision**: Simple arithmetic average of True Range over 14 periods.

**Rationale**: The spec (Assumptions section) explicitly requires simple average for transparency and testability. Wilder's EMA introduces an exponential smoothing factor that requires a "warm-up" of ~3× the period to stabilise, making unit test assertions non-deterministic without careful seeding. Simple average is fully deterministic: same 14 bars always produce the same ATR.

**Alternatives considered**:
- Wilder's EMA (exponential smoothing α = 1/period): Standard in MetaTrader indicators; produces smoother ATR but requires more bars to initialise and is harder to hand-verify in tests. Rejected per spec Assumption note.
- Rolling median: More robust to outliers but not a standard ATR formula — deviates from XAUUSD convention used in volatility_filter.py.

---

## D-002: Reference ATR — Rolling Window Size and Method

**Decision**: Reference ATR = arithmetic mean of the last 20 computed ATR values (one ATR value per bar).

**Rationale**: 20 H1 ATR values = ~one trading week of H1 data. This captures the recent "normal" volatility without being too sensitive to single spikes. The 20-period window is already referenced in spec004 (session-filters) as the basis for the `reference_atr` parameter passed to `classify_regime()`. Keeping the same value ensures the volatility filter ratio is consistent with what was expected when spec004 was written.

**Alternatives considered**:
- 50-period window: More stable but slower to react to regime shifts (e.g., post-Fed announcement). Rejected as too slow for XAUUSD intraday.
- Exponential weighted mean: Smoother but non-deterministic for tests. Rejected for same reason as D-001.

---

## D-003: Cache Invalidation Strategy

**Decision**: Per-timeframe in-memory dict. Cache entry is invalidated (marked stale) when `ATRService.refresh(timeframe, bars)` is called by the main orchestrator on each bar close. On stale + refresh-failure → return last valid value and log warning.

**Rationale**: The bot already processes bar events (new H1 bar, new H4 bar, new D1 bar) in its main loop (spec008 orchestrator). The orchestrator will call `ATRService.refresh(timeframe, bars)` at each bar-close event. The ATR module does not need to track time independently — it receives bars from the caller. This is the same pattern used by all other stateless modules in this codebase.

**Alternatives considered**:
- Time-based expiry (e.g., expire after 60s): Would require the module to track wall-clock time, adding a hidden dependency. Rejected.
- Invalidate on every call (no cache): Causes unnecessary recomputation on every tick. Rejected per FR-009.

---

## D-004: ATRService — Stateful Class vs Module-Level Functions

**Decision**: Stateful `ATRService` class holding a `dict[Timeframe, ATRCache]`.

**Rationale**: The cache must persist between calls (bar-to-bar), so state is required. A class makes ownership explicit (one instance per bot session) and is consistent with `ExecutionEngine`, `RiskManager`, and `TradeGate` in the existing codebase, all of which are stateful classes.

**Alternatives considered**:
- Module-level dict (global cache): Implicit global state complicates test isolation. Rejected.
- Dataclass with frozen state: Cannot update cache in-place. Rejected.

---

## D-005: Separation of MT5 Data Fetch from ATR Computation

**Decision**: `ATRService.refresh()` accepts a pre-fetched `list[OHLCVBar]` — it does NOT call MT5 directly. The caller (orchestrator) fetches OHLCV bars via `market_data.py` (spec001) and passes them to `refresh()`.

**Rationale**: Keeps the ATR module pure and testable without any MT5 mock. All existing pure modules in this codebase (lot_calculator, bos_choch, fvg, etc.) follow this pattern — no MT5 imports outside `src/broker/`. Decoupling also allows the ATR module to be backtested with historical CSV data without any broker connection.

**Alternatives considered**:
- ATRService fetches its own OHLCV data: Would require MT5 dependency inside `src/analysis/`, violating the pattern established across the codebase. Rejected.

---

## D-006: Timeframe Enum

**Decision**: `Timeframe` enum with members M5, H1, H4, D1. Numeric values = MT5 timeframe constants (5, 16385, 16388, 16408) to allow direct passthrough to `market_data.get_ohlcv(timeframe.value, ...)` without a separate mapping.

**Rationale**: MT5 Python API uses integer constants for timeframes. Encoding them as enum values eliminates a translation table and avoids any possibility of passing a wrong integer. Follows the same pattern as `Direction` enum in `src/engine/models.py`.

**Alternatives considered**:
- String enum ("M5", "H1", etc.): Readable but requires a separate mapping to MT5 integers at the broker layer. Rejected.

---

## D-007: Minimum Bar Count — Graceful Degradation

**Decision**: If available bars < ATR period (14), return `ATRReading` with `current_atr = None` (Python `Optional[float]`). Callers check `is_ready(timeframe)` before using. On startup, fetch `period + reference_period + 5` bars (14 + 20 + 5 = 39 bars) to populate both the ATR window and the reference ATR window immediately.

**Rationale**: Prevents callers from using an ATR of 0.0 (which would cause division-by-zero in lot sizing) or an unreliable ATR from too few bars. The `is_ready()` guard is the canonical check — consistent with how `TradeGate.can_trade()` works in spec004.

**Alternatives considered**:
- Raise an exception on insufficient data: Forces every caller to wrap in try/except. Rejected — too verbose.
- Return 0.0 as sentinel: Division-by-zero risk in `lot_calculator.py`. Rejected per FR-011 spirit.

---

## D-008: Invalid Bar Handling

**Decision**: `validate_ohlcv_bars()` filters out bars where `High < Low` or `Close <= 0`. Filtered bars are logged at WARNING level with the bar's timestamp. Computation proceeds on the valid subset. If all bars are invalid, treat as insufficient data (D-007 applies).

**Rationale**: XAUUSD occasionally has data glitches during market open or extreme news events. Silent skipping with a log warning allows computation to continue on the valid data while giving operators visibility into data quality issues.

---

## D-009: Integration Points with Existing Modules

| Caller | ATRService method | Data returned |
|--------|-----------------|---------------|
| `volatility_filter.check_volatility()` (spec004) | `get_h1_readings()` | `(current_atr: float, reference_atr: float)` |
| `lot_calculator.calculate_sl_price()` (spec003) | `get_d1_atr()` | `d1_atr: float` |
| `lot_calculator.calculate_lot_size()` (spec003) | `get_adaptive_multipliers(regime)` | `AdaptiveMultipliers` |
| Orchestrator (spec008) | `refresh(timeframe, bars)` | `ATRReading` (logged) |

---

## D-010: Config Namespace

**Decision**: New `analysis.atr` section in `config.yaml`. Keeps ATR config separate from `filters`, `risk`, and `execution` sections already in use.

```yaml
analysis:
  atr:
    period: 14
    reference_period: 20
    adaptive_multipliers:
      sl:
        LOW: 1.0
        NORMAL: 1.5
        EXTREME: 2.0
      tp:
        LOW: 2.0
        NORMAL: 3.0
        EXTREME: 4.0
```
