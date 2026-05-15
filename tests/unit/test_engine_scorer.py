"""Unit tests for scorer.py — confidence scoring and EntrySignal assembly.

Tests run BEFORE implementation (TDD). All tests must fail initially (ImportError
from missing scorer.py), then pass after T020 implementation.
"""

import json
import pytest
from unittest.mock import patch

from src.engine.models import (
    Bias, Direction, FVGStatus, OBStatus, SignalType, SweepType,
    FVGZone, OrderBlock, LiquiditySweep, EntrySignal,
)
from src.engine.scorer import score_and_assemble

DEFAULT_WEIGHTS = {
    "bos_or_choch": 0.40,
    "fvg": 0.30,
    "order_block": 0.20,
    "liquidity_sweep": 0.10,
}
THRESHOLD = 0.65


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fvg_long():
    return FVGZone(top=1910.0, bottom=1905.0, midpoint=1907.5,
                   direction=Direction.LONG, status=FVGStatus.UNFILLED, candle_index=10)

def _fvg_short():
    return FVGZone(top=1920.0, bottom=1915.0, midpoint=1917.5,
                   direction=Direction.SHORT, status=FVGStatus.UNFILLED, candle_index=10)

def _ob_long():
    return OrderBlock(top=1908.0, bottom=1905.0,
                      direction=Direction.LONG, status=OBStatus.ACTIVE, candle_index=8)

def _ob_short():
    return OrderBlock(top=1918.0, bottom=1915.0,
                      direction=Direction.SHORT, status=OBStatus.ACTIVE, candle_index=8)

def _sweep_low():
    return LiquiditySweep(sweep_level=1895.0, close_price=1896.0,
                          type=SweepType.LOW, candle_index=15)

def _sweep_high():
    return LiquiditySweep(sweep_level=1925.0, close_price=1924.0,
                          type=SweepType.HIGH, candle_index=15)


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def test_full_confluence_bullish_confidence_is_one():
    """BOS+FVG+OB+LS → confidence=1.0, direction=LONG (FR-018)"""
    sig = score_and_assemble(
        SignalType.BOS_BULLISH, [_fvg_long()], [_ob_long()], [_sweep_low()],
        DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
    )
    assert sig.direction == Direction.LONG
    assert sig.confidence == pytest.approx(1.0)


def test_bos_fvg_ob_confidence_is_0_90():
    """BOS+FVG+OB → confidence=0.90, accepted (FR-018)"""
    sig = score_and_assemble(
        SignalType.BOS_BULLISH, [_fvg_long()], [_ob_long()], [],
        DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
    )
    assert sig.direction == Direction.LONG
    assert sig.confidence == pytest.approx(0.90)


def test_bos_fvg_confidence_is_0_70_accepted():
    """BOS+FVG → confidence=0.70, accepted (above threshold)"""
    sig = score_and_assemble(
        SignalType.BOS_BULLISH, [_fvg_long()], [], [],
        DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
    )
    assert sig.direction == Direction.LONG
    assert sig.confidence == pytest.approx(0.70)


def test_bos_only_confidence_0_40_rejected(tmp_path):
    """BOS only → confidence=0.40 < 0.65 → direction=NONE (FR-019)"""
    with patch("src.engine.scorer.FALSE_SIGNALS_LOG", str(tmp_path / "fs.json")):
        sig = score_and_assemble(
            SignalType.BOS_BULLISH, [], [], [],
            DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
        )
    assert sig.direction == Direction.NONE
    assert sig.confidence == pytest.approx(0.40)


def test_bos_ob_confidence_0_60_rejected(tmp_path):
    """BOS+OB → confidence=0.60 < 0.65 → rejected (FR-019)"""
    with patch("src.engine.scorer.FALSE_SIGNALS_LOG", str(tmp_path / "fs.json")):
        sig = score_and_assemble(
            SignalType.BOS_BULLISH, [], [_ob_long()], [],
            DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
        )
    assert sig.direction == Direction.NONE
    assert sig.confidence == pytest.approx(0.60)


def test_signal_type_none_returns_none_without_logging():
    """signal_type=NONE → NONE signal immediately; scorer must not log (no structural event)"""
    sig = score_and_assemble(
        SignalType.NONE, [], [], [],
        DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
    )
    assert sig.direction == Direction.NONE
    assert sig.confidence == pytest.approx(0.0)
    assert sig.entry_zone_top == 0.0
    assert sig.entry_zone_bottom == 0.0


def test_sweep_low_adds_bonus_to_bullish():
    """Sweep LOW adds liquidity_sweep weight to bullish signal confidence"""
    without_sweep = score_and_assemble(
        SignalType.BOS_BULLISH, [_fvg_long()], [_ob_long()], [],
        DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
    )
    with_sweep = score_and_assemble(
        SignalType.BOS_BULLISH, [_fvg_long()], [_ob_long()], [_sweep_low()],
        DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
    )
    assert with_sweep.confidence > without_sweep.confidence
    assert with_sweep.confidence == pytest.approx(1.0)


def test_sweep_high_does_not_bonus_bullish():
    """Sweep HIGH is bearish confirmation and must NOT add bonus to a LONG signal"""
    sig = score_and_assemble(
        SignalType.BOS_BULLISH, [_fvg_long()], [_ob_long()], [_sweep_high()],
        DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
    )
    # BOS + FVG + OB = 0.90; no sweep bonus
    assert sig.confidence == pytest.approx(0.90)


def test_invalidated_ob_not_counted(tmp_path):
    """INVALIDATED OB does not contribute weight to confidence"""
    ob_inv = OrderBlock(top=1908.0, bottom=1905.0,
                        direction=Direction.LONG, status=OBStatus.INVALIDATED, candle_index=8)
    # With INVALIDATED OB: only BOS + FVG = 0.70 (not BOS + FVG + OB = 0.90)
    sig = score_and_assemble(
        SignalType.BOS_BULLISH, [_fvg_long()], [ob_inv], [],
        DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
    )
    assert sig.confidence == pytest.approx(0.70)


def test_filled_fvg_not_counted(tmp_path):
    """FILLED FVG does not contribute weight to confidence"""
    fvg_filled = FVGZone(top=1910.0, bottom=1905.0, midpoint=1907.5,
                         direction=Direction.LONG, status=FVGStatus.FILLED, candle_index=10)
    with patch("src.engine.scorer.FALSE_SIGNALS_LOG", str(tmp_path / "fs.json")):
        sig = score_and_assemble(
            SignalType.BOS_BULLISH, [fvg_filled], [], [],
            DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
        )
    # FILLED FVG not counted → BOS only = 0.40, below threshold
    assert sig.direction == Direction.NONE
    assert sig.confidence == pytest.approx(0.40)


# ---------------------------------------------------------------------------
# False signals log (FR-023)
# ---------------------------------------------------------------------------

def test_rejected_signal_logged_with_required_fields(tmp_path):
    """Rejected signal written to false_signals.json with timestamp, reason, confidence"""
    log_path = tmp_path / "fs.json"
    with patch("src.engine.scorer.FALSE_SIGNALS_LOG", str(log_path)):
        score_and_assemble(
            SignalType.BOS_BULLISH, [], [], [],
            DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
        )
    assert log_path.exists()
    lines = [l for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert "timestamp" in entry
    assert "confidence" in entry
    assert "reason" in entry


def test_multiple_rejected_signals_append_to_log(tmp_path):
    """Multiple rejected signals accumulate as separate lines in false_signals.json"""
    log_path = tmp_path / "fs.json"
    with patch("src.engine.scorer.FALSE_SIGNALS_LOG", str(log_path)):
        for _ in range(3):
            score_and_assemble(
                SignalType.BOS_BULLISH, [], [], [],
                DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
            )
    lines = [l for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 3


# ---------------------------------------------------------------------------
# Entry zone (D-004, FR-017)
# ---------------------------------------------------------------------------

def test_ob_takes_priority_over_fvg_as_entry_zone():
    """OB body (top/bottom) is primary entry_zone when OB is present (D-004)"""
    ob  = _ob_long()
    fvg = _fvg_long()
    sig = score_and_assemble(
        SignalType.BOS_BULLISH, [fvg], [ob], [],
        DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
    )
    assert sig.entry_zone_top    == ob.top
    assert sig.entry_zone_bottom == ob.bottom


def test_fvg_fallback_when_no_ob():
    """FVG boundaries used as entry_zone when no active OB present (D-004)"""
    fvg = _fvg_long()
    sig = score_and_assemble(
        SignalType.BOS_BULLISH, [fvg], [], [],
        DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
    )
    assert sig.entry_zone_top    == fvg.top
    assert sig.entry_zone_bottom == fvg.bottom


def test_none_signal_entry_zone_is_zero(tmp_path):
    """NONE signal has entry_zone_top = entry_zone_bottom = 0.0 (data-model invariant)"""
    with patch("src.engine.scorer.FALSE_SIGNALS_LOG", str(tmp_path / "fs.json")):
        sig = score_and_assemble(
            SignalType.BOS_BULLISH, [], [], [],
            DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
        )
    assert sig.entry_zone_top    == 0.0
    assert sig.entry_zone_bottom == 0.0


# ---------------------------------------------------------------------------
# HTF bias filter (FR-021)
# ---------------------------------------------------------------------------

def test_bearish_bias_rejects_long_signal(tmp_path):
    """BEARISH htf_bias discards LONG signal even with full confluence (FR-021)"""
    with patch("src.engine.scorer.FALSE_SIGNALS_LOG", str(tmp_path / "fs.json")):
        sig = score_and_assemble(
            SignalType.BOS_BULLISH, [_fvg_long()], [_ob_long()], [_sweep_low()],
            DEFAULT_WEIGHTS, THRESHOLD, Bias.BEARISH,
        )
    assert sig.direction == Direction.NONE


def test_bullish_bias_allows_long_signal():
    """BULLISH htf_bias passes aligned LONG signals"""
    sig = score_and_assemble(
        SignalType.BOS_BULLISH, [_fvg_long()], [_ob_long()], [],
        DEFAULT_WEIGHTS, THRESHOLD, Bias.BULLISH,
    )
    assert sig.direction == Direction.LONG


def test_neutral_bias_allows_long():
    """NEUTRAL htf_bias does not filter LONG signals"""
    sig = score_and_assemble(
        SignalType.BOS_BULLISH, [_fvg_long()], [_ob_long()], [],
        DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
    )
    assert sig.direction == Direction.LONG


def test_neutral_bias_allows_short():
    """NEUTRAL htf_bias does not filter SHORT signals"""
    sig = score_and_assemble(
        SignalType.BOS_BEARISH, [_fvg_short()], [_ob_short()], [],
        DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
    )
    assert sig.direction == Direction.SHORT


# ---------------------------------------------------------------------------
# Components and reason (FR-020, FR-024)
# ---------------------------------------------------------------------------

def test_accepted_signal_has_non_empty_components():
    """Accepted signal includes components list for downstream audit (FR-024)"""
    sig = score_and_assemble(
        SignalType.BOS_BULLISH, [_fvg_long()], [_ob_long()], [_sweep_low()],
        DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
    )
    assert len(sig.components) >= 1
    assert any("BOS" in c for c in sig.components)


def test_reason_always_populated_for_none_signal():
    """reason is non-empty even for NONE signals (FR-020)"""
    sig = score_and_assemble(
        SignalType.NONE, [], [], [],
        DEFAULT_WEIGHTS, THRESHOLD, Bias.NEUTRAL,
    )
    assert sig.reason
    assert len(sig.reason) > 0
