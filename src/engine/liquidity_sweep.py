"""Liquidity Sweep (Stop-Hunt) detection for the SMC Engine.

Identifies clusters of equal highs/lows and detects when price wicks beyond 
them but closes back inside, indicating a liquidity grab.
"""

import pandas as pd
from src.engine.models import LiquiditySweep, SweepType

def detect_liquidity_sweeps(df: pd.DataFrame, pip_tolerance: float = 0.5, lookback: int = 20) -> list[LiquiditySweep]:
    """Detect stop-hunt events (liquidity sweeps) in the provided OHLCV data.

    A sweep high occurs when price wicks above equal highs and closes below.
    A sweep low occurs when price wicks below equal lows and closes above.

    Args:
        df: OHLCV DataFrame with columns [high, low, close].
        pip_tolerance: Price difference to consider highs/lows as 'equal' ($0.50 for XAUUSD).
        lookback: Number of previous candles to look back for equal levels.

    Returns:
        List of LiquiditySweep objects, newest first.
    """
    if df.empty or len(df) < 2:
        return []

    # Pre-extract as numpy arrays — avoids repeated pandas row-access overhead (SC-005)
    highs  = df["high"].to_numpy(dtype=float)
    lows   = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    n      = len(df)

    sweeps = []

    # Iterate through the DataFrame starting from the first possible sweep candle.
    # We need at least 2 previous candles to form 'equal' levels.
    for i in range(2, n):
        window_start = max(0, i - lookback)

        # 1. Look for Equal Highs in the lookback window
        prev_highs = highs[window_start:i].tolist()
        for cluster in _find_level_clusters(prev_highs, pip_tolerance):
            sweep_level = max(cluster)
            # SMC Rule: Wick above equal highs AND same candle closes back below (FR-014)
            if highs[i] > sweep_level and closes[i] < sweep_level:
                sweeps.append(LiquiditySweep(
                    sweep_level=float(sweep_level),
                    close_price=float(closes[i]),
                    type=SweepType.HIGH,
                    candle_index=int(i),
                ))
                break  # Record once for the highest cluster per candle

        # 2. Look for Equal Lows in the lookback window
        prev_lows = lows[window_start:i].tolist()
        for cluster in _find_level_clusters(prev_lows, pip_tolerance):
            sweep_level = min(cluster)
            # SMC Rule: Wick below equal lows AND same candle closes back above (FR-015)
            if lows[i] < sweep_level and closes[i] > sweep_level:
                sweeps.append(LiquiditySweep(
                    sweep_level=float(sweep_level),
                    close_price=float(closes[i]),
                    type=SweepType.LOW,
                    candle_index=int(i),
                ))
                break

    # Return newest first
    return sweeps[::-1]

def _find_level_clusters(levels: list[float], tolerance: float) -> list[list[float]]:
    """Group levels into clusters of 'equal' values.
    
    A cluster must contain at least two levels.
    """
    if not levels:
        return []
    
    # Sort levels to find neighbors within tolerance
    sorted_levels = sorted(levels)
    clusters = []
    
    if not sorted_levels:
        return []
        
    current_cluster = [sorted_levels[0]]
    
    for level in sorted_levels[1:]:
        # If this level is close to the previous one in the sorted list
        if level - current_cluster[-1] <= tolerance:
            current_cluster.append(level)
        else:
            # Cluster finished, check if it has at least 2 points
            if len(current_cluster) >= 2:
                clusters.append(current_cluster)
            current_cluster = [level]
            
    # Check the last cluster
    if len(current_cluster) >= 2:
        clusters.append(current_cluster)
        
    return clusters
