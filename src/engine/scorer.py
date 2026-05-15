"""Confidence scoring and EntrySignal assembly for the SMC Engine.

FR-017: entry_zone uses OB body (primary) or FVG boundaries (fallback) — D-004.
FR-018: confidence = additive weighted sum of present components — D-005.
FR-019: signals below confidence_threshold discarded, direction set to NONE.
FR-020: reason string populated for every signal.
FR-021: htf_bias filter — misaligned signals discarded after scoring.
FR-023: discarded signals logged to false_signals.json (timestamp, reason, confidence).
FR-024: accepted signals include components list for downstream audit.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.engine.models import (
    Bias, Direction, EntrySignal, FVGStatus, FVGZone,
    LiquiditySweep, OBStatus, OrderBlock, SignalType, SweepType,
)

# Module-level path lets tests monkeypatch without touching the filesystem
FALSE_SIGNALS_LOG = "logs/false_signals.json"

_BULLISH_TYPES = {SignalType.BOS_BULLISH, SignalType.CHOCH_BULLISH}
_BEARISH_TYPES = {SignalType.BOS_BEARISH, SignalType.CHOCH_BEARISH}


def score_and_assemble(
    signal_type: SignalType,
    fvg_zones: list[FVGZone],
    order_blocks: list[OrderBlock],
    sweeps: list[LiquiditySweep],
    weights: dict[str, float],
    threshold: float,
    htf_bias: Bias,
) -> EntrySignal:
    """Combine detected SMC components into a single scored EntrySignal.

    Scoring (D-005): additive weighted sum — each present component adds its weight.
    Entry zone (D-004): OB body top/bottom is primary; FVG boundaries are fallback.
    Threshold (FR-019): confidence < threshold → discard, log, return NONE signal.
    HTF bias (FR-021): misaligned direction discarded after scoring so the log
                       entry records the full computed confidence for audit.

    Args:
        signal_type:  BOS/CHoCH event from detect_structure_break().
        fvg_zones:    All FVG zones from detect_fvg_zones().
        order_blocks: All OBs from detect_order_blocks().
        sweeps:       All sweeps from detect_liquidity_sweeps().
        weights:      Component weights dict (keys: bos_or_choch, fvg, order_block, liquidity_sweep).
        threshold:    Minimum confidence to accept a signal (default 0.65 from config).
        htf_bias:     Caller-provided higher-timeframe bias enum.

    Returns:
        EntrySignal with direction LONG/SHORT/NONE. Never None. Never raises.
    """
    now = datetime.now(timezone.utc)

    # No structural event → return NONE immediately; nothing to score or log
    if signal_type == SignalType.NONE:
        return _none_signal("No structural event detected", now)

    direction = Direction.LONG if signal_type in _BULLISH_TYPES else Direction.SHORT

    # --- Score all aligned components ---
    components: list[str] = [signal_type.value]
    confidence: float = float(weights.get("bos_or_choch", 0.40))

    # UNFILLED FVG zones aligned with signal direction (FR-005–FR-008)
    aligned_fvgs = [z for z in fvg_zones
                    if z.status == FVGStatus.UNFILLED and z.direction == direction]
    if aligned_fvgs:
        confidence += float(weights.get("fvg", 0.30))
        components.append("FVG")

    # Non-invalidated OBs aligned with signal direction (FR-009–FR-012)
    aligned_obs = [ob for ob in order_blocks
                   if ob.status != OBStatus.INVALIDATED and ob.direction == direction]
    if aligned_obs:
        confidence += float(weights.get("order_block", 0.20))
        components.append("OB")

    # Liquidity sweep bonus: LOW sweep = bullish stop-hunt, HIGH sweep = bearish stop-hunt
    # A sweep in the OPPOSITE direction to price confirms the reversal (FR-013–FR-016)
    confirming_sweep_type = SweepType.LOW if direction == Direction.LONG else SweepType.HIGH
    if any(s.type == confirming_sweep_type for s in sweeps):
        confidence += float(weights.get("liquidity_sweep", 0.10))
        components.append("Liquidity Sweep")

    confidence = min(1.0, max(0.0, confidence))
    reason = " + ".join(components)

    # --- HTF bias filter (FR-021) — applied after scoring for audit transparency ---
    if (htf_bias == Bias.BULLISH and direction == Direction.SHORT) or \
       (htf_bias == Bias.BEARISH and direction == Direction.LONG):
        return _log_and_discard(
            f"{reason} [HTF bias mismatch: {htf_bias.value}]",
            confidence, signal_type, now,
        )

    # --- Threshold filter (FR-019) ---
    if confidence < threshold:
        return _log_and_discard(reason, confidence, signal_type, now)

    # --- Determine entry zone (D-004, FR-017) ---
    # OB body is primary; FVG boundaries are fallback; 0.0 when neither is present
    entry_top = entry_bottom = 0.0
    if aligned_obs:
        entry_top, entry_bottom = aligned_obs[0].top, aligned_obs[0].bottom
    elif aligned_fvgs:
        entry_top, entry_bottom = aligned_fvgs[0].top, aligned_fvgs[0].bottom

    return EntrySignal(
        direction=direction,
        confidence=confidence,
        entry_zone_top=entry_top,
        entry_zone_bottom=entry_bottom,
        reason=reason,
        components=components,
        signal_type=signal_type,
        timestamp=now,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _none_signal(reason: str, now: datetime) -> EntrySignal:
    """Return NONE EntrySignal for guard conditions — zero entry zone (FR-022)."""
    return EntrySignal(
        direction=Direction.NONE,
        confidence=0.0,
        entry_zone_top=0.0,
        entry_zone_bottom=0.0,
        reason=reason,
        components=[],
        signal_type=SignalType.NONE,
        timestamp=now,
    )


def _log_and_discard(
    reason: str,
    confidence: float,
    signal_type: SignalType,
    now: datetime,
) -> EntrySignal:
    """Write discarded signal to false_signals.json and return NONE EntrySignal (FR-023)."""
    entry = {
        "timestamp": now.isoformat(),
        "reason": reason,
        "confidence": round(confidence, 4),
        "signal_type": signal_type.value,
    }
    try:
        log_path = Path(FALSE_SIGNALS_LOG)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # I/O failure must not block signal production

    return EntrySignal(
        direction=Direction.NONE,
        confidence=confidence,
        entry_zone_top=0.0,
        entry_zone_bottom=0.0,
        reason=reason,
        components=[],
        signal_type=signal_type,
        timestamp=now,
    )
