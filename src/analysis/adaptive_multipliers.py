"""Adaptive SL/TP multiplier selection based on VolatilityRegime (FR-007, FR-008).

Multipliers are read from config['analysis']['atr']['adaptive_multipliers']
so they are fully configurable without code changes (FR-013).
"""
from __future__ import annotations

from src.analysis.models import AdaptiveMultipliers, VolatilityRegime


def get_adaptive_multipliers(
    regime: VolatilityRegime,
    config: dict,
) -> AdaptiveMultipliers:
    """Return SL and TP multipliers for the given VolatilityRegime (FR-007, FR-008).

    Reads from config['analysis']['atr']['adaptive_multipliers']['sl'/'tp'][regime.value].
    Raises KeyError with a descriptive message if the config section is missing or incomplete.
    """
    try:
        mults = config["analysis"]["atr"]["adaptive_multipliers"]
        sl = float(mults["sl"][regime.value])
        tp = float(mults["tp"][regime.value])
    except KeyError as exc:
        raise KeyError(
            f"Missing adaptive_multipliers config for regime '{regime.value}': "
            f"expected config['analysis']['atr']['adaptive_multipliers']['sl'/'tp']['{regime.value}']. "
            f"Missing key: {exc}"
        ) from exc
    return AdaptiveMultipliers(sl_multiplier=sl, tp_multiplier=tp, regime=regime)
