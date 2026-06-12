"""H4 Bias Engine — detects and classifies H4 structural bias (spec007).

Classifies market structure as BULLISH, BEARISH, or RANGING using fractal
swing points from H4 bars. RANGING blocks all downstream trade entries.

Interface contract: refresh() → get_bias() / is_ready()
Designed for LSTM replaceability — pipeline accesses only these 3 methods.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from loguru import logger

from src.analysis.models import OHLCVBar
from src.engine.models import Bias, SwingPoint
from src.engine.swing import detect_swing_points


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class H4BiasResult:
    """Output of one H4 bias classification cycle.

    bias:        BULLISH | BEARISH | RANGING
    strength:    fraction of aligned HH/HL (or LH/LL) pairs; 0.0 when RANGING
    swing_count: confirmed swing points used in this classification
    timestamp:   UTC time of result
    """
    bias: Bias
    strength: float
    swing_count: int
    timestamp: datetime


# ---------------------------------------------------------------------------
# Core classification logic
# ---------------------------------------------------------------------------

def classify_bias(
    swing_points: list[SwingPoint],
    bullish_threshold: float,
    bearish_threshold: float,
) -> tuple[Bias, float]:
    """Classify H4 market structure from confirmed swing points.

    SMC rule: separate swings into HIGHs and LOWs, count consecutive HH/HL
    pairs for bullish and LH/LL pairs for bearish. Strength = fraction of
    aligned pairs across both series; clipped to [0.0, 1.0].

    Returns:
        (Bias.RANGING, 0.0) when fewer than 2 swings of the same type exist —
        not enough structure to determine direction.
    """
    highs = sorted(
        [sp for sp in swing_points if sp.type == "HIGH"],
        key=lambda s: s.candle_index,
    )
    lows = sorted(
        [sp for sp in swing_points if sp.type == "LOW"],
        key=lambda s: s.candle_index,
    )

    # Need at least 2 of each type to form a consecutive pair
    if len(highs) < 2 or len(lows) < 2:
        return Bias.RANGING, 0.0

    high_pairs = len(highs) - 1
    low_pairs = len(lows) - 1

    hh_count = sum(1 for i in range(1, len(highs)) if highs[i].price > highs[i - 1].price)
    hl_count = sum(1 for i in range(1, len(lows))  if lows[i].price  > lows[i - 1].price)
    lh_count = sum(1 for i in range(1, len(highs)) if highs[i].price < highs[i - 1].price)
    ll_count = sum(1 for i in range(1, len(lows))  if lows[i].price  < lows[i - 1].price)

    # Bullish requires BOTH highs and lows to trend upward simultaneously
    bullish_strength = min(hh_count / high_pairs, hl_count / low_pairs)
    # Bearish requires BOTH highs and lows to trend downward simultaneously
    bearish_strength = min(lh_count / high_pairs, ll_count / low_pairs)

    bullish_strength = min(1.0, max(0.0, bullish_strength))
    bearish_strength = min(1.0, max(0.0, bearish_strength))

    if bullish_strength >= bullish_threshold and bullish_strength >= bearish_strength:
        return Bias.BULLISH, bullish_strength
    if bearish_strength >= bearish_threshold and bearish_strength > bullish_strength:
        return Bias.BEARISH, bearish_strength
    return Bias.RANGING, 0.0


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class H4BiasService:
    """Detects and caches H4 structural bias for the signal pipeline.

    Reads config['analysis']['h4_bias'] at startup; raises KeyError if the
    block is missing so misconfiguration fails fast rather than silently
    defaulting to the wrong bias.
    """

    def __init__(self, config: dict) -> None:
        """Raises KeyError when config['analysis']['h4_bias'] is absent."""
        cfg = config["analysis"]["h4_bias"]
        self._lookback_bars: int = int(cfg["lookback_bars"])
        self._fractal_n: int = int(cfg["fractal_n"])
        self._bullish_threshold: float = float(cfg["bullish_strength_threshold"])
        self._bearish_threshold: float = float(cfg["bearish_strength_threshold"])
        self._last_result: Optional[H4BiasResult] = None

    def refresh(self, h4_bars: list[OHLCVBar]) -> H4BiasResult:
        """Classify H4 bias; cache and return the result.

        Returns RANGING/0.0 without updating the cache when fewer than
        lookback_bars are provided (cold start before history accumulates).
        Never raises — I/O or computation failures fall back to last cached
        result or RANGING so the pipeline is never blocked.
        """
        now = datetime.now(timezone.utc)

        try:
            if len(h4_bars) < self._lookback_bars:
                # Cold start: not enough history; do not advance the cache so
                # is_ready() stays False until a real classification runs.
                return H4BiasResult(bias=Bias.RANGING, strength=0.0, swing_count=0, timestamp=now)

            df = pd.DataFrame([
                {
                    "open": b.open, "high": b.high, "low": b.low,
                    "close": b.close, "volume": b.volume, "timestamp": b.timestamp,
                }
                for b in h4_bars
            ])

            swing_points = detect_swing_points(
                df, fractal_n=self._fractal_n, lookback=self._lookback_bars,
            )

            bias, strength = classify_bias(
                swing_points, self._bullish_threshold, self._bearish_threshold,
            )

            result = H4BiasResult(
                bias=bias,
                strength=strength,
                swing_count=len(swing_points),
                timestamp=now,
            )

            # Audit trail: log every bias direction change (spec007 US5)
            if self._last_result is not None and result.bias != self._last_result.bias:
                logger.info(
                    "H4 bias transition: {} → {} | strength={:.2f}",
                    self._last_result.bias.value, result.bias.value, result.strength,
                )

            self._last_result = result
            return result

        except Exception as exc:
            logger.warning("H4BiasService.refresh() failed: {}; returning last cached result", exc)
            if self._last_result is not None:
                return self._last_result
            return H4BiasResult(bias=Bias.RANGING, strength=0.0, swing_count=0, timestamp=now)

    def get_bias(self) -> H4BiasResult:
        """Return the last cached result, or RANGING/0.0 before first refresh."""
        if self._last_result is None:
            return H4BiasResult(
                bias=Bias.RANGING,
                strength=0.0,
                swing_count=0,
                timestamp=datetime.now(timezone.utc),
            )
        return self._last_result

    def is_ready(self) -> bool:
        """True only after at least one successful refresh() with enough bars."""
        return self._last_result is not None
