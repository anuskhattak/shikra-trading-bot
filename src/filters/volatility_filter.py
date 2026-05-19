"""Volatility filter — classifies ATR ratio as LOW/NORMAL/EXTREME and blocks abnormal regimes."""
from datetime import datetime, timezone

from src.filters.models import (
    FilterDecision,
    FilterResult,
    VolatilityReading,
    VolatilityRegime,
)


def classify_regime(current_atr: float, reference_atr: float, config: dict) -> VolatilityReading:
    """Classify volatility regime from ATR ratio. Returns full VolatilityReading with all 5 fields."""
    vol_cfg = config["filters"]["volatility"]
    low_ratio = vol_cfg["low_atr_ratio"]
    extreme_ratio = vol_cfg["extreme_atr_ratio"]
    ratio = current_atr / reference_atr

    if ratio < low_ratio:
        regime = VolatilityRegime.LOW
    elif ratio >= extreme_ratio:
        regime = VolatilityRegime.EXTREME
    else:
        regime = VolatilityRegime.NORMAL

    return VolatilityReading(
        regime=regime,
        current_atr=current_atr,
        reference_atr=reference_atr,
        ratio=ratio,
        timestamp=datetime.now(timezone.utc),
    )


def check_volatility(current_atr: float, reference_atr: float, config: dict) -> FilterDecision:
    """Gate trade on volatility regime. Blocks LOW and EXTREME; metric_value = ATR ratio float."""
    reading = classify_regime(current_atr, reference_atr, config)

    if reading.regime == VolatilityRegime.LOW:
        return FilterDecision(
            filter_name="volatility",
            result=FilterResult.BLOCKED,
            reason="VOLATILITY_TOO_LOW",
            metric_value=reading.ratio,
            timestamp=reading.timestamp,
        )
    if reading.regime == VolatilityRegime.EXTREME:
        return FilterDecision(
            filter_name="volatility",
            result=FilterResult.BLOCKED,
            reason="VOLATILITY_EXTREME",
            metric_value=reading.ratio,
            timestamp=reading.timestamp,
        )
    return FilterDecision(
        filter_name="volatility",
        result=FilterResult.ALLOWED,
        reason="ALLOWED",
        metric_value=reading.ratio,
        timestamp=reading.timestamp,
    )
