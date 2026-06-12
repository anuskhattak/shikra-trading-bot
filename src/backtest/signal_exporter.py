"""JSONL signal export for backtest analysis — spec009 T019."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from src.analysis.models import Timeframe
from src.filters.volatility_filter import classify_regime
from src.orchestrator.models import PipelineContext

_FALLBACK_VOL_CFG = {
    "filters": {"volatility": {"low_atr_ratio": 0.5, "extreme_atr_ratio": 5.0}}
}


def export_signals(
    contexts: list[PipelineContext],
    output_path: str | Path,
    config: Optional[dict] = None,
) -> None:
    """Write one JSON object per line (JSONL) — NOT a JSON array.

    Every row contains exactly 13 fields:
    timestamp, signal_type, confidence, filter_result, filter_reason,
    direction, entry_price, sl_price, atr_h1_current, atr_h1_reference,
    volatility_ratio, volatility_regime, trade_placed.
    """
    cfg = config or _FALLBACK_VOL_CFG
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        for ctx in contexts:
            row = _build_row(ctx, cfg)
            f.write(json.dumps(row) + "\n")


def _build_row(ctx: PipelineContext, config: dict) -> dict:
    signal = ctx.entry_signal
    fr     = ctx.filter_result
    h1     = ctx.atr_readings.get(Timeframe.H1)
    risk   = ctx.risk_calc

    # ATR fields
    atr_current   = h1.current_atr   if h1 else None
    atr_reference = h1.reference_atr if h1 else None
    vol_ratio     = h1.ratio         if h1 else None

    # Volatility regime — derived from ATR ratio using filter thresholds
    vol_regime = "UNKNOWN"
    if h1 and h1.current_atr is not None and h1.reference_atr is not None:
        try:
            reading = classify_regime(h1.current_atr, h1.reference_atr, config)
            vol_regime = reading.regime.value
        except Exception:
            vol_regime = "UNKNOWN"

    # Filter result and reason
    fr_str = fr.final_result.value if fr else "N/A"
    filter_reason = "N/A"
    if fr is not None:
        blocked = [d for d in fr.decisions if d.result.value == "BLOCKED"]
        filter_reason = blocked[0].reason if blocked else "ALLOWED"

    # Entry price — midpoint of signal zone when direction is not NONE
    entry_price = None
    if signal and signal.direction.value != "NONE":
        entry_price = (signal.entry_zone_top + signal.entry_zone_bottom) / 2.0

    return {
        "timestamp":         ctx.now_utc.isoformat(),
        "signal_type":       signal.signal_type.value if signal else "NONE",
        "confidence":        signal.confidence         if signal else 0.0,
        "filter_result":     fr_str,
        "filter_reason":     filter_reason,
        "direction":         signal.direction.value    if signal else "NONE",
        "entry_price":       entry_price,
        "sl_price":          risk.sl_price             if risk   else None,
        "atr_h1_current":    atr_current,
        "atr_h1_reference":  atr_reference,
        "volatility_ratio":  vol_ratio,
        "volatility_regime": vol_regime,
        "trade_placed":      risk is not None,
    }
