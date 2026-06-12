"""Top-level orchestrator for the SMC Signal Detection Engine.

Single public entry point consumed by downstream modules (risk manager, order executor).

FR-021: htf_bias accepted as a caller-provided parameter; engine does not derive it.
FR-022: generate_signal always returns a valid EntrySignal — never None, never raises.
NFR-002: Stateless — full recompute on every call from the provided DataFrame.
NFR-003: No MetaTrader5 import anywhere in src/engine/.
SC-005:  Target < 100ms for generate_signal on a 200-row DataFrame.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from src.engine.bos_choch import detect_structure_break
from src.engine.fvg import detect_fvg_zones
from src.engine.liquidity_sweep import detect_liquidity_sweeps
from src.engine.models import Bias, Direction, EntrySignal, SignalType
from src.engine.order_block import detect_order_blocks
from src.engine.scorer import score_and_assemble
from src.engine.swing import detect_swing_points

_CONFIG_PATH = Path("config.yaml")

_BULLISH_TYPES = {SignalType.BOS_BULLISH, SignalType.CHOCH_BULLISH}
_BEARISH_TYPES = {SignalType.BOS_BEARISH, SignalType.CHOCH_BEARISH}

# Conversion: 1 pip for XAUUSD = $0.10 (spec: 5 pips = $0.50)
_PIPS_TO_DOLLARS = 0.10


def generate_signal(
    df: pd.DataFrame,
    htf_bias: Bias = Bias.NEUTRAL,
    htf_bias_strength: float = 0.0,
    config: dict | None = None,
) -> EntrySignal:
    """Run all SMC detectors in sequence and return a scored EntrySignal.

    Stateless: full recompute from the provided DataFrame on every call (NFR-002).
    Safe: any unexpected exception returns NONE signal instead of raising (FR-022).
    Broker-agnostic: operates purely on pandas DataFrames (NFR-003).

    Args:
        df:                OHLCV DataFrame — columns [time, open, high, low, close, tick_volume].
        htf_bias:          Pre-computed higher-timeframe bias from the caller (default NEUTRAL).
        htf_bias_strength: Strength score of the H4 bias (0.0–1.0, default 0.0).
        config:            Optional override dict merged onto config.yaml smc_engine values.

    Returns:
        EntrySignal with direction LONG, SHORT, or NONE. Never None. Never raises.
    """
    try:
        cfg = _load_config(config)

        fractal_n    = int(cfg.get("fractal_n", 2))
        lookback     = int(cfg.get("lookback_window", 20))
        threshold    = float(cfg.get("confidence_threshold", 0.65))
        min_candles  = int(cfg.get("min_candles", 50))
        pip_tol      = float(cfg.get("equal_level_tolerance_pips", 5)) * _PIPS_TO_DOLLARS
        weights: dict[str, float] = dict(cfg.get("weights", {
            "bos_or_choch": 0.40,
            "fvg":           0.30,
            "order_block":   0.20,
            "liquidity_sweep": 0.10,
        }))

        # Guard: insufficient candle history (Assumption 2)
        if len(df) < min_candles:
            return _none_signal(f"Insufficient candles: {len(df)} < {min_candles}")

        # Step 1 — Fractal swing points (FR-001)
        swing_points = detect_swing_points(df, fractal_n=fractal_n, lookback=lookback)

        # Step 2 — Structure break: BOS or CHoCH (FR-002–FR-004)
        signal_type, _ = detect_structure_break(df, swing_points)

        # Step 3 — Direction filter for downstream detectors
        if signal_type in _BULLISH_TYPES:
            direction_filter = Direction.LONG
        elif signal_type in _BEARISH_TYPES:
            direction_filter = Direction.SHORT
        else:
            direction_filter = None

        # Step 4 — Fair Value Gaps, filtered by signal direction (FR-005–FR-008)
        fvg_zones = detect_fvg_zones(df, direction_filter=direction_filter)

        # Step 5 — Order Blocks; BOS candle is always the last candle in df (FR-009–FR-012)
        if signal_type != SignalType.NONE:
            order_blocks = detect_order_blocks(df, signal_type, len(df) - 1)
        else:
            order_blocks = []

        # Step 6 — Liquidity sweeps (FR-013–FR-016)
        sweeps = detect_liquidity_sweeps(df, pip_tolerance=pip_tol, lookback=lookback)

        # Step 7 — Score and assemble EntrySignal (FR-017–FR-024)
        return score_and_assemble(
            signal_type=signal_type,
            fvg_zones=fvg_zones,
            order_blocks=order_blocks,
            sweeps=sweeps,
            weights=weights,
            threshold=threshold,
            htf_bias=htf_bias,
            htf_bias_strength=htf_bias_strength,
        )

    except Exception:  # noqa: BLE001
        # FR-022: engine must never propagate an exception to the caller
        return _none_signal("Engine error — unexpected exception during signal generation")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _load_config(override: dict | None) -> dict:
    """Load smc_engine section from config.yaml, then merge caller overrides."""
    cfg: dict = {}
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        cfg = dict(raw.get("smc_engine", {}))
    if override:
        cfg.update(override)
    return cfg


def _none_signal(reason: str) -> EntrySignal:
    """Return NONE EntrySignal for guard conditions (FR-022)."""
    return EntrySignal(
        direction=Direction.NONE,
        confidence=0.0,
        entry_zone_top=0.0,
        entry_zone_bottom=0.0,
        reason=reason,
        components=[],
        signal_type=SignalType.NONE,
        timestamp=datetime.now(timezone.utc),
    )
