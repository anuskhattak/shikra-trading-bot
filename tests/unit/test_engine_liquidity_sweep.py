import pytest
import pandas as pd
import numpy as np
from src.engine.liquidity_sweep import detect_liquidity_sweeps
from src.engine.models import SweepType

def test_detect_sweep_high_success():
    """Test successful detection of a liquidity sweep high."""
    # Create flat DF with no sweeps in background
    df = pd.DataFrame({
        "high": [1900.0] * 50,
        "low": [1890.0] * 50,
        "close": [1900.0] * 50, # Close at high to avoid HIGH sweep
        "open": [1900.0] * 50
    })
    
    # 1. Create two equal highs at index 10 and 20
    sweep_level = 1950.0
    df.loc[10, "high"] = sweep_level
    df.loc[20, "high"] = sweep_level + 0.2  # Within 0.5 tolerance
    
    # 2. Create the sweep candle at index 30
    df.loc[30, "high"] = sweep_level + 1.0  # Wicks above
    df.loc[30, "close"] = sweep_level - 0.5 # Closes back below
    
    sweeps = detect_liquidity_sweeps(df, pip_tolerance=0.5)
    
    target_sweeps = [s for s in sweeps if s.candle_index == 30 and s.type == SweepType.HIGH]
    assert len(target_sweeps) == 1
    sweep = target_sweeps[0]
    assert sweep.sweep_level == 1950.2
    assert sweep.close_price == sweep_level - 0.5

def test_detect_sweep_low_success():
    """Test successful detection of a liquidity sweep low."""
    df = pd.DataFrame({
        "high": [1900.0] * 50,
        "low": [1890.0] * 50,
        "close": [1900.0] * 50,
        "open": [1900.0] * 50
    })
    
    # 1. Create two equal lows
    sweep_level = 1850.0
    df.loc[10, "low"] = sweep_level
    df.loc[20, "low"] = sweep_level - 0.3  # Within 0.5 tolerance
    
    # 2. Create the sweep candle
    df.loc[30, "low"] = sweep_level - 1.0   # Wicks below
    df.loc[30, "close"] = sweep_level + 0.5  # Closes back above
    
    sweeps = detect_liquidity_sweeps(df, pip_tolerance=0.5)
    
    target_sweeps = [s for s in sweeps if s.candle_index == 30 and s.type == SweepType.LOW]
    assert len(target_sweeps) == 1
    sweep = target_sweeps[0]
    assert sweep.sweep_level == 1849.7
    assert sweep.close_price == sweep_level + 0.5

def test_no_sweep_when_close_above_high():
    """No sweep high if the candle closes above the equal highs."""
    df = pd.DataFrame({
        "high": [1900.0] * 50,
        "low": [1890.0] * 50,
        "close": [1900.0] * 50,
        "open": [1900.0] * 50
    })
    sweep_level = 1950.0
    df.loc[10, "high"] = sweep_level
    df.loc[20, "high"] = sweep_level
    
    # Wick above AND close above
    df.loc[30, "high"] = sweep_level + 1.0
    df.loc[30, "close"] = sweep_level + 0.5
    
    sweeps = detect_liquidity_sweeps(df, pip_tolerance=0.5)
    assert not any(s.candle_index == 30 for s in sweeps)

def test_no_sweep_outside_tolerance():
    """No sweep if highs are too far apart to be considered 'equal'."""
    df = pd.DataFrame({
        "high": [1900.0] * 50,
        "low": [1890.0] * 50,
        "close": [1900.0] * 50,
        "open": [1900.0] * 50
    })
    df.loc[10, "high"] = 1950.0
    df.loc[20, "high"] = 1951.0 # 1.0 diff > 0.5 tolerance
    
    # Wick above 1951.0
    df.loc[30, "high"] = 1952.0
    df.loc[30, "close"] = 1949.0
    
    sweeps = detect_liquidity_sweeps(df, pip_tolerance=0.5)
    assert len(sweeps) == 0

def test_multiple_equal_levels_clustering():
    """Test that multiple highs within tolerance form a cluster."""
    df = pd.DataFrame({
        "high": [1900.0] * 50,
        "low": [1890.0] * 50,
        "close": [1900.0] * 50,
        "open": [1900.0] * 50
    })
    df.loc[10, "high"] = 1950.0
    df.loc[15, "high"] = 1950.2
    df.loc[20, "high"] = 1949.8
    
    # Sweep all of them
    df.loc[30, "high"] = 1951.0
    df.loc[30, "close"] = 1949.0
    
    sweeps = detect_liquidity_sweeps(df, pip_tolerance=0.5)
    
    target_sweeps = [s for s in sweeps if s.candle_index == 30]
    assert len(target_sweeps) == 1
    assert target_sweeps[0].sweep_level == 1950.2


def test_empty_df_returns_empty_list():
    """Handle empty or small DataFrames gracefully."""
    df = pd.DataFrame(columns=["time", "open", "high", "low", "close", "tick_volume"])
    assert detect_liquidity_sweeps(df, 0.5) == []
    
    df = pd.DataFrame({"high": [1900.0], "low": [1800.0], "close": [1850.0]})
    assert detect_liquidity_sweeps(df, 0.5) == []
