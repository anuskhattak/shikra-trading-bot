"""ATR Calibration Module — spec006 public API."""
from src.analysis.adaptive_multipliers import get_adaptive_multipliers
from src.analysis.atr_calculator import compute_atr, compute_true_range, validate_ohlcv_bars
from src.analysis.atr_service import ATRService
from src.analysis.h4_bias import H4BiasResult, H4BiasService
from src.analysis.models import (
    ATRCache,
    ATRReading,
    AdaptiveMultipliers,
    OHLCVBar,
    Timeframe,
    VolatilityRegime,
)
from src.analysis.reference_atr import compute_reference_atr

__all__ = [
    "Timeframe",
    "OHLCVBar",
    "VolatilityRegime",
    "AdaptiveMultipliers",
    "ATRReading",
    "ATRCache",
    "ATRService",
    "compute_atr",
    "compute_true_range",
    "validate_ohlcv_bars",
    "compute_reference_atr",
    "get_adaptive_multipliers",
    "H4BiasService",
    "H4BiasResult",
]
