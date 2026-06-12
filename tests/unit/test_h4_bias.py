"""Unit tests for src/analysis/h4_bias.py — spec007 T014–T034.

Bar layouts are hand-crafted so detect_swing_points() produces exactly
the swing sequences needed to verify classify_bias() and H4BiasService.
All tests use fractal_n=1 and small lookback so 6-8 bars are sufficient.
"""

from datetime import datetime, timezone

import pytest

from src.analysis.h4_bias import H4BiasResult, H4BiasService, classify_bias
from src.analysis.models import OHLCVBar
from src.engine.models import Bias, Direction, SignalType
from src.engine.scorer import score_and_assemble

_TS = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

# Config shared by T014–T016: lookback=6, fractal_n=1 keeps tests small
_CFG_6 = {
    "analysis": {
        "h4_bias": {
            "lookback_bars": 6,
            "fractal_n": 1,
            "bullish_strength_threshold": 0.60,
            "bearish_strength_threshold": 0.60,
        }
    }
}

# Config for ranging test that needs 8 bars to fit 3 swings of each type
_CFG_8 = {
    "analysis": {
        "h4_bias": {
            "lookback_bars": 8,
            "fractal_n": 1,
            "bullish_strength_threshold": 0.60,
            "bearish_strength_threshold": 0.60,
        }
    }
}

# Config for cold-start test: lookback=10 so 5 bars are insufficient
_CFG_10 = {
    "analysis": {
        "h4_bias": {
            "lookback_bars": 10,
            "fractal_n": 1,
            "bullish_strength_threshold": 0.60,
            "bearish_strength_threshold": 0.60,
        }
    }
}


def _bar(high: float, low: float) -> OHLCVBar:
    """Create a minimal valid OHLCVBar with open/close at midpoint."""
    mid = (high + low) / 2
    return OHLCVBar(open=mid, high=high, low=low, close=mid, volume=1000.0, timestamp=_TS)


# ── T014 ────────────────────────────────────────────────────────────────────

def test_bullish_bias_hh_hl():
    """6 bars producing swing HIGHs [20, 30] (HH) and LOWs [5, 12] (HL).

    detect_swing_points with fractal_n=1 confirms swings at indices 1-4.
    Both consecutive HIGH and LOW sequences trend upward → BULLISH.

    Bar layout (highs/lows only):
        idx: 0   1   2   3   4   5
        H:   10  20  12  30  22  25
        L:    9  15   5  18  12  20
    """
    bars = [
        _bar(10, 9),
        _bar(20, 15),   # swing HIGH at price 20
        _bar(12, 5),    # swing LOW at price 5
        _bar(30, 18),   # swing HIGH at price 30  (HH: 30 > 20)
        _bar(22, 12),   # swing LOW at price 12   (HL: 12 > 5)
        _bar(25, 20),
    ]
    svc = H4BiasService(_CFG_6)
    result = svc.refresh(bars)

    assert result.bias == Bias.BULLISH
    assert result.strength >= 0.60


# ── T015 ────────────────────────────────────────────────────────────────────

def test_bearish_bias_lh_ll():
    """6 bars producing swing HIGHs [30, 25] (LH) and LOWs [10, 5] (LL).

    Both consecutive HIGH and LOW sequences trend downward → BEARISH.

    Bar layout:
        idx: 0   1   2   3   4   5
        H:   20  30  15  25  10  15
        L:   15  20  10  18   5  10
    """
    bars = [
        _bar(20, 15),
        _bar(30, 20),   # swing HIGH at price 30
        _bar(15, 10),   # swing LOW at price 10
        _bar(25, 18),   # swing HIGH at price 25  (LH: 25 < 30)
        _bar(10, 5),    # swing LOW at price 5    (LL: 5 < 10)
        _bar(15, 10),
    ]
    svc = H4BiasService(_CFG_6)
    result = svc.refresh(bars)

    assert result.bias == Bias.BEARISH
    assert result.strength >= 0.60


# ── T016 ────────────────────────────────────────────────────────────────────

def test_ranging_mixed_structure():
    """8 bars with alternating swing direction: HH then LH, HL then LL.

    Each direction gets exactly half the pairs (0.5 strength each), which
    falls below the 0.6 threshold → RANGING.

    Bar layout:
        idx: 0    1    2    3    4    5    6    7
        H:   1.0  3.0  2.5  5.0  3.5  4.0  2.0  3.0
        L:   0.5  2.0  1.0  4.0  2.0  3.0  1.5  2.5

    Swing HIGHs: [3.0, 5.0, 4.0] — one HH then one LH
    Swing LOWs:  [1.0, 2.0, 1.5] — one HL then one LL
    """
    bars = [
        _bar(1.0, 0.5),
        _bar(3.0, 2.0),   # swing HIGH at 3.0
        _bar(2.5, 1.0),   # swing LOW at 1.0
        _bar(5.0, 4.0),   # swing HIGH at 5.0  (HH)
        _bar(3.5, 2.0),   # swing LOW at 2.0   (HL)
        _bar(4.0, 3.0),   # swing HIGH at 4.0  (LH)
        _bar(2.0, 1.5),   # swing LOW at 1.5   (LL)
        _bar(3.0, 2.5),
    ]
    svc = H4BiasService(_CFG_8)
    result = svc.refresh(bars)

    assert result.bias == Bias.RANGING


# ── T017 ────────────────────────────────────────────────────────────────────

def test_cold_start_insufficient_bars():
    """Fewer bars than lookback_bars returns RANGING with strength 0.0; no exception."""
    bars = [_bar(float(i + 1), float(i)) for i in range(5)]  # only 5 bars, lookback=10

    svc = H4BiasService(_CFG_10)
    result = svc.refresh(bars)   # must not raise

    assert result.bias == Bias.RANGING
    assert result.strength == 0.0
    assert svc.is_ready() is False   # cache not populated — not a real classification


# ── T018 ────────────────────────────────────────────────────────────────────

def test_ranging_blocks_scorer():
    """RANGING bias is the first check in score_and_assemble() regardless of signal_type."""
    result = score_and_assemble(
        signal_type=SignalType.BOS_BULLISH,
        fvg_zones=[],
        order_blocks=[],
        sweeps=[],
        weights={},
        threshold=0.65,
        htf_bias=Bias.RANGING,
    )

    assert result.direction == Direction.NONE
    assert "H4_RANGING" in result.reason
    assert result.confidence == 0.0


# ── T028 ────────────────────────────────────────────────────────────────────

def test_alignment_boost_added():
    """BULLISH bias + LONG signal: H4_ALIGN appended to components and confidence boosted.

    Base confidence (bos_or_choch default weight = 0.40) is raised by the alignment
    boost and MTF multiplier when bias and direction agree.
    """
    base_weight = 0.40   # default bos_or_choch weight when weights={}

    result = score_and_assemble(
        signal_type=SignalType.BOS_BULLISH,
        fvg_zones=[],
        order_blocks=[],
        sweeps=[],
        weights={},
        threshold=0.50,          # intentionally low so boosted signal passes threshold
        htf_bias=Bias.BULLISH,
        htf_bias_strength=0.85,
    )

    assert "H4_ALIGN" in result.components
    assert result.confidence > base_weight    # boost raised it above the raw component score


# ── T029 ────────────────────────────────────────────────────────────────────

def test_mtf_multiplier_applied():
    """MTF multiplier: (0.50 base + 0.20 h4_alignment) × 1.30 = min(1.0, 0.91).

    Weights engineered so component confidence = 0.50 (bos_or_choch only).
    After h4_alignment: 0.70.  After mtf_boost × 1.30: 0.91.
    """
    weights = {"bos_or_choch": 0.50, "h4_alignment": 0.20, "mtf_boost": 1.30}

    result = score_and_assemble(
        signal_type=SignalType.BOS_BULLISH,
        fvg_zones=[],
        order_blocks=[],
        sweeps=[],
        weights=weights,
        threshold=0.65,
        htf_bias=Bias.BULLISH,
        htf_bias_strength=0.85,
    )

    assert result.confidence == pytest.approx(min(1.0, 0.70 * 1.30))
    assert "H4_ALIGN" in result.components


# ── T032 ────────────────────────────────────────────────────────────────────

def test_entry_signal_carries_bias():
    """Accepted signal has h4_bias and h4_bias_strength populated on the returned object.

    Uses bos_or_choch=0.50 + h4_alignment=0.20 = 0.70, mtf_boost default=1.30 →
    final confidence = min(1.0, 0.91) > threshold 0.65 → signal accepted (direction LONG).
    Verifies the bias audit fields survive through to the caller.
    """
    result = score_and_assemble(
        signal_type=SignalType.BOS_BULLISH,
        fvg_zones=[],
        order_blocks=[],
        sweeps=[],
        weights={"bos_or_choch": 0.50, "h4_alignment": 0.20},
        threshold=0.65,
        htf_bias=Bias.BULLISH,
        htf_bias_strength=0.75,
    )

    assert result.direction == Direction.LONG
    assert result.h4_bias == Bias.BULLISH
    assert result.h4_bias_strength == pytest.approx(0.75)


# ── T030 ────────────────────────────────────────────────────────────────────

def test_pipeline_wires_h4_service():
    """Mock H4BiasService returning BULLISH propagates into ctx.h4_bias_result and entry_signal.

    Stage 0 stores the bias in ctx.  Stage 2 embeds it in EntrySignal regardless of
    whether the signal direction is NONE — all scorer return paths carry htf_bias (T023).
    """
    from unittest.mock import MagicMock

    from src.analysis.models import ATRReading, Timeframe
    from src.orchestrator.models import PipelineContext
    from src.orchestrator.pipeline import run_pipeline

    now = _TS

    mock_h4 = MagicMock()
    mock_h4.refresh.return_value = H4BiasResult(
        bias=Bias.BULLISH, strength=0.80, swing_count=4, timestamp=now,
    )

    # Return a valid H1 ATR so the pipeline proceeds past the early-exit guard
    h1_reading = ATRReading(
        timeframe=Timeframe.H1, current_atr=10.0, reference_atr=9.0,
        ratio=1.11, bar_count=50, timestamp=now,
    )
    mock_atr = MagicMock()
    mock_atr.refresh.return_value = h1_reading

    # 50+ bars required: generate_signal() has a min_candles=50 guard; below that it
    # returns a _none_signal() that doesn't carry htf_bias through (pre-T023 early exit).
    bars = [_bar(float(i + 1), float(i)) for i in range(60)]
    ctx = PipelineContext(
        signal_id="t030-test",
        timeframe=Timeframe.H1,
        bars={Timeframe.H1: bars, Timeframe.H4: bars},
        now_utc=now,
        spread_usd=0.30,
        news_events=[],
        mode="backtest",
    )

    config = {"smc_engine": {"confidence_threshold": 0.65, "weights": {}}, "risk": {}}

    result_ctx = run_pipeline(ctx, mock_atr, config, mock_h4)

    assert result_ctx.h4_bias_result is not None
    assert result_ctx.h4_bias_result.bias == Bias.BULLISH
    assert result_ctx.entry_signal is not None
    assert result_ctx.entry_signal.h4_bias == Bias.BULLISH


# ── T033 ────────────────────────────────────────────────────────────────────

def test_no_counter_trend_boost():
    """BULLISH bias + SHORT signal: no H4_ALIGN, no MTF multiplier, signal discarded.

    BOS_BEARISH → direction SHORT. BULLISH+SHORT alignment block does NOT fire
    (only BULLISH+LONG triggers it). HTF bias filter then discards the counter-trend
    signal — final result is direction NONE with no H4_ALIGN component.
    """
    result = score_and_assemble(
        signal_type=SignalType.BOS_BEARISH,
        fvg_zones=[],
        order_blocks=[],
        sweeps=[],
        weights={},
        threshold=0.65,
        htf_bias=Bias.BULLISH,
        htf_bias_strength=0.80,
    )

    assert result.direction == Direction.NONE
    assert "H4_ALIGN" not in result.components
    assert "HTF bias mismatch" in result.reason


# ── T034 ────────────────────────────────────────────────────────────────────

def test_neutral_bias_no_block_no_boost():
    """NEUTRAL bias + LONG signal: not blocked, not boosted, accepted on own merit.

    NEUTRAL skips the RANGING block and never triggers the alignment boost.
    bos_or_choch=0.70 pushes confidence above threshold without any H4 help,
    confirming NEUTRAL is a pure pass-through — neither filter nor amplifier.
    """
    result = score_and_assemble(
        signal_type=SignalType.BOS_BULLISH,
        fvg_zones=[],
        order_blocks=[],
        sweeps=[],
        weights={"bos_or_choch": 0.70},
        threshold=0.65,
        htf_bias=Bias.NEUTRAL,
        htf_bias_strength=0.0,
    )

    assert result.direction == Direction.LONG
    assert "H4_ALIGN" not in result.components
    assert result.confidence == pytest.approx(0.70)
