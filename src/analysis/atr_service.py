"""ATRService — stateful per-timeframe ATR cache and orchestrator (spec006).

Bridges raw OHLCV data (spec001) to:
  - volatility_filter.check_volatility() via get_h1_readings()     (spec004)
  - lot_calculator.calculate_sl_price()  via get_d1_atr()          (spec003)
  - lot_calculator.calculate_lot_size()  via get_adaptive_multipliers()

Design: no MT5 imports; caller (orchestrator) pre-fetches OHLCV and passes bars in (D-005).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from src.analysis.adaptive_multipliers import get_adaptive_multipliers
from src.analysis.atr_calculator import compute_atr, validate_ohlcv_bars
from src.analysis.models import (
    ATRCache,
    ATRReading,
    AdaptiveMultipliers,
    OHLCVBar,
    Timeframe,
    VolatilityRegime,
)
from src.analysis.reference_atr import compute_reference_atr


class ATRService:
    """Per-session stateful ATR cache. One instance per bot run."""

    def __init__(self, config: dict) -> None:
        """Initialise with empty cache for all four timeframes.

        Raises KeyError if config['analysis']['atr'] section is missing (FR-013).
        """
        if "analysis" not in config or "atr" not in config.get("analysis", {}):
            raise KeyError(
                "config must contain 'analysis.atr' section. "
                "Add it to config.yaml (see specs/006-atr-calibration/quickstart.md)."
            )
        self._config   = config
        self._atr_cfg  = config["analysis"]["atr"]
        self._period   = int(self._atr_cfg.get("period", 14))
        self._ref_period = int(self._atr_cfg.get("reference_period", 20))

        # Cache: None = no data yet for this timeframe
        self._cache: dict[Timeframe, Optional[ATRCache]] = {tf: None for tf in Timeframe}
        # Rolling ATR history per timeframe for reference_atr computation
        self._atr_history: dict[Timeframe, list[float]] = {tf: [] for tf in Timeframe}

    # ── public mutating API ──────────────────────────────────────────────────

    def refresh(self, timeframe: Timeframe, bars: list[OHLCVBar]) -> ATRReading:
        """Compute fresh ATR from pre-fetched OHLCV bars; update cache (FR-009, FR-010).

        On failure: preserves last cached value, marks is_fresh=False, logs WARNING (FR-011).
        Never raises — returns last valid reading or empty reading on first-call failure.
        """
        now = datetime.now(timezone.utc)
        try:
            valid_bars = validate_ohlcv_bars(bars)
            current_atr = compute_atr(valid_bars, self._period)

            if current_atr is not None:
                self._atr_history[timeframe].append(current_atr)

            reference_atr = compute_reference_atr(
                self._atr_history[timeframe], self._ref_period
            )
            ratio: Optional[float] = None
            if current_atr is not None and reference_atr is not None:
                ratio = current_atr / reference_atr

            reading = ATRReading(
                timeframe=timeframe,
                current_atr=current_atr,
                reference_atr=reference_atr,
                ratio=ratio,
                bar_count=len(valid_bars),
                timestamp=now,
            )
            self._cache[timeframe] = ATRCache(
                reading=reading,
                is_fresh=True,
                last_refreshed=now,
            )
            return reading

        except Exception as exc:  # pragma: no cover — defensive catch for unexpected errors
            logger.warning(
                "ATR refresh failed for {} at {}: {}", timeframe.name, now, exc
            )
            cached = self._cache[timeframe]
            if cached is not None:
                cached.is_fresh = False
                return cached.reading
            # No prior cache — return empty reading so caller gets None ATR
            return ATRReading(
                timeframe=timeframe,
                current_atr=None,
                reference_atr=None,
                ratio=None,
                bar_count=0,
                timestamp=now,
            )

    def mark_stale(self, timeframe: Timeframe) -> None:
        """Mark a timeframe's cache as stale (called by orchestrator before bar refresh)."""
        cached = self._cache[timeframe]
        if cached is not None:
            cached.is_fresh = False

    # ── public read-only API ─────────────────────────────────────────────────

    def get_atr(self, timeframe: Timeframe) -> Optional[float]:
        """Return cached current_atr for timeframe, or None if cache is empty."""
        cached = self._cache[timeframe]
        if cached is None:
            return None
        return cached.reading.current_atr

    def get_h1_readings(self) -> tuple[Optional[float], Optional[float]]:
        """Return (current_h1_atr, reference_h1_atr) for volatility_filter (FR-005)."""
        cached = self._cache[Timeframe.H1]
        if cached is None:
            return None, None
        return cached.reading.current_atr, cached.reading.reference_atr

    def get_d1_atr(self) -> Optional[float]:
        """Return cached D1 ATR for lot_calculator.calculate_sl_price() (FR-006)."""
        return self.get_atr(Timeframe.D1)

    def get_adaptive_multipliers(self, regime: VolatilityRegime) -> AdaptiveMultipliers:
        """Return SL/TP multipliers for the given regime (FR-007, FR-008)."""
        return get_adaptive_multipliers(regime, self._config)

    def is_ready(self, timeframe: Timeframe) -> bool:
        """Return True if cache has a valid (non-None) ATR reading for this timeframe."""
        atr = self.get_atr(timeframe)
        return atr is not None
