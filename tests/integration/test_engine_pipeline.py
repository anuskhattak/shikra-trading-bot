"""Integration tests for the full SMC engine pipeline.

Scope: generate_signal() orchestrates all detectors end-to-end.
Run separately: pytest tests/integration/test_engine_pipeline.py -v

Tests must FAIL before smc_engine.py is created (ImportError), then
pass after T020/T021/T022 implementation.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import patch

from src.engine.models import Bias, Direction, EntrySignal
from src.engine.smc_engine import generate_signal

# Inline config so tests are isolated from file I/O on config.yaml
TEST_CONFIG = {
    "fractal_n": 2,
    "lookback_window": 20,
    "equal_level_tolerance_pips": 5,
    "confidence_threshold": 0.65,
    "weights": {
        "bos_or_choch": 0.40,
        "fvg": 0.30,
        "order_block": 0.20,
        "liquidity_sweep": 0.10,
    },
    "min_candles": 50,
}


# ---------------------------------------------------------------------------
# DataFrame factories
# ---------------------------------------------------------------------------

def _flat_df(n: int) -> pd.DataFrame:
    """Minimal flat DataFrame for smoke testing — no detectable structure."""
    times = [datetime(2024, 1, 1) + timedelta(hours=i) for i in range(n)]
    return pd.DataFrame({
        "time": times,
        "open":        np.full(n, 1900.0),
        "high":        np.full(n, 1902.0),
        "low":         np.full(n, 1898.0),
        "close":       np.full(n, 1900.0),
        "tick_volume": np.full(n, 500, dtype=int),
    })


def _bos_bullish_df() -> pd.DataFrame:
    """60-candle DataFrame engineered to produce BOS_BULLISH with FVG + OB.

    Design:
      - Swing HIGH at index 50 (price=1915, fractal_n=2 confirmed by indices 48-52)
      - Swing LOW  at index 44 (price=1890, fractal_n=2 confirmed by indices 42-46)
      - Bullish FVG at indices 55-57: candle[55].high=1901 < candle[57].low=1905
      - Bearish OB  at index 58  (open=1913, close=1911 → bearish candle before BOS)
      - BOS candle  at index 59  (close=1916 > swing HIGH 1915 → BOS_BULLISH)

    Expected: generate_signal returns direction=LONG, confidence=0.90 (BOS+FVG+OB)
    """
    n = 60
    opens  = np.full(n, 1900.0)
    closes = np.full(n, 1900.0)
    highs  = np.full(n, 1902.0)
    lows   = np.full(n, 1898.0)

    # Swing HIGH at index 50: highs[48]=highs[49]=1902 < 1915, highs[51]=highs[52]=1902 < 1915
    highs[50] = 1915.0

    # Swing LOW at index 44: lows[42]=lows[43]=1898 > 1890, lows[45]=lows[46]=1898 > 1890
    lows[44] = 1890.0

    # Bullish FVG: candle[55].high (1901) < candle[57].low (1905)
    highs[55] = 1901.0; closes[55] = 1900.0; opens[55] = 1899.0; lows[55] = 1898.0
    highs[56] = 1908.0; closes[56] = 1907.0; opens[56] = 1901.0; lows[56] = 1900.0
    highs[57] = 1912.0; closes[57] = 1910.0; opens[57] = 1907.0; lows[57] = 1905.0

    # Bearish OB candle at 58 (last bearish before BOS)
    opens[58] = 1913.0; closes[58] = 1911.0; highs[58] = 1914.0; lows[58] = 1910.0

    # BOS candle at 59: close=1916 > swing HIGH at 1915
    opens[59] = 1912.0; closes[59] = 1916.0; highs[59] = 1917.0; lows[59] = 1910.0

    times = [datetime(2024, 1, 1) + timedelta(hours=i) for i in range(n)]
    return pd.DataFrame({
        "time": times, "open": opens, "high": highs,
        "low": lows, "close": closes,
        "tick_volume": np.full(n, 500, dtype=int),
    })


# ---------------------------------------------------------------------------
# Pipeline basics (FR-022, NFR-002)
# ---------------------------------------------------------------------------

class TestPipelineBasics:
    def test_returns_entry_signal_never_none(self, tmp_path):
        """generate_signal always returns EntrySignal — never None (FR-022)"""
        with patch("src.engine.scorer.FALSE_SIGNALS_LOG", str(tmp_path / "fs.json")):
            result = generate_signal(_flat_df(60), htf_bias=Bias.NEUTRAL, config=TEST_CONFIG)
        assert result is not None
        assert isinstance(result, EntrySignal)

    def test_below_min_candles_returns_none_direction(self):
        """<50 candles → direction=NONE (Assumption 2, FR-022)"""
        result = generate_signal(_flat_df(30), htf_bias=Bias.NEUTRAL, config=TEST_CONFIG)
        assert result.direction == Direction.NONE

    def test_confidence_always_in_range(self, tmp_path):
        """confidence is always in [0.0, 1.0] (FR-018)"""
        with patch("src.engine.scorer.FALSE_SIGNALS_LOG", str(tmp_path / "fs.json")):
            result = generate_signal(_flat_df(60), htf_bias=Bias.NEUTRAL, config=TEST_CONFIG)
        assert 0.0 <= result.confidence <= 1.0

    def test_reason_always_non_empty_string(self, tmp_path):
        """reason is always a non-empty string (FR-020)"""
        with patch("src.engine.scorer.FALSE_SIGNALS_LOG", str(tmp_path / "fs.json")):
            result = generate_signal(_flat_df(60), htf_bias=Bias.NEUTRAL, config=TEST_CONFIG)
        assert isinstance(result.reason, str)
        assert len(result.reason) > 0

    def test_deterministic_same_input_same_output(self, tmp_path):
        """Identical DataFrame input produces identical output — stateless (NFR-002, SC-006)"""
        df = _bos_bullish_df()
        with patch("src.engine.scorer.FALSE_SIGNALS_LOG", str(tmp_path / "fs.json")):
            sig1 = generate_signal(df.copy(), htf_bias=Bias.NEUTRAL, config=TEST_CONFIG)
            sig2 = generate_signal(df.copy(), htf_bias=Bias.NEUTRAL, config=TEST_CONFIG)
        assert sig1.direction == sig2.direction
        assert sig1.confidence == pytest.approx(sig2.confidence)
        assert sig1.reason == sig2.reason

    def test_never_raises_on_valid_dataframe(self, tmp_path):
        """generate_signal must never raise an exception on well-formed DataFrame (FR-022)"""
        with patch("src.engine.scorer.FALSE_SIGNALS_LOG", str(tmp_path / "fs.json")):
            try:
                result = generate_signal(_bos_bullish_df(), htf_bias=Bias.NEUTRAL, config=TEST_CONFIG)
                assert isinstance(result, EntrySignal)
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"generate_signal raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# BOS + FVG + OB end-to-end (US5 acceptance scenario 1)
# ---------------------------------------------------------------------------

class TestBOSFVGOBPipeline:
    def test_engineered_data_produces_long_signal(self, tmp_path):
        """BOS+FVG+OB aligned bullish → direction=LONG (US5 acceptance scenario 1)"""
        with patch("src.engine.scorer.FALSE_SIGNALS_LOG", str(tmp_path / "fs.json")):
            sig = generate_signal(_bos_bullish_df(), htf_bias=Bias.NEUTRAL, config=TEST_CONFIG)
        assert sig.direction == Direction.LONG

    def test_engineered_data_confidence_at_least_bos_fvg(self, tmp_path):
        """BOS+FVG+OB → confidence ≥ 0.70 (BOS=0.40 + FVG=0.30 at minimum)"""
        with patch("src.engine.scorer.FALSE_SIGNALS_LOG", str(tmp_path / "fs.json")):
            sig = generate_signal(_bos_bullish_df(), htf_bias=Bias.NEUTRAL, config=TEST_CONFIG)
        assert sig.confidence >= 0.70

    def test_accepted_signal_entry_zone_is_sensible(self, tmp_path):
        """Accepted signal: entry_zone_top ≥ entry_zone_bottom > 0 (FR-017)"""
        with patch("src.engine.scorer.FALSE_SIGNALS_LOG", str(tmp_path / "fs.json")):
            sig = generate_signal(_bos_bullish_df(), htf_bias=Bias.NEUTRAL, config=TEST_CONFIG)
        if sig.direction != Direction.NONE:
            assert sig.entry_zone_top >= sig.entry_zone_bottom
            assert sig.entry_zone_bottom > 0.0



# ---------------------------------------------------------------------------
# Performance benchmark (SC-005, SC-006) — T024
# ---------------------------------------------------------------------------

class TestPerformance:
    def test_200_candle_signal_under_100ms(self, tmp_path):
        """generate_signal on 200-row DataFrame completes in < 100ms (SC-005).

        One warm-up call is made first to exclude Python module-import overhead;
        the timer measures pure computation cost (numpy array access, loop logic).
        """
        import time
        df = _flat_df(200)
        with patch("src.engine.scorer.FALSE_SIGNALS_LOG", str(tmp_path / "fs.json")):
            # Warm up: loads all modules into memory so import cost is not timed
            generate_signal(df, htf_bias=Bias.NEUTRAL, config=TEST_CONFIG)
            # Timed call
            start = time.perf_counter()
            generate_signal(df, htf_bias=Bias.NEUTRAL, config=TEST_CONFIG)
            elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 100, f"Expected < 100ms, got {elapsed_ms:.1f}ms"

    def test_deterministic_confidence_sc006(self, tmp_path):
        """Identical DataFrame + config always produces identical confidence (SC-006)."""
        df = _bos_bullish_df()
        results = []
        with patch("src.engine.scorer.FALSE_SIGNALS_LOG", str(tmp_path / "fs.json")):
            for _ in range(3):
                sig = generate_signal(df.copy(), htf_bias=Bias.NEUTRAL, config=TEST_CONFIG)
                results.append(sig.confidence)
        assert all(r == pytest.approx(results[0]) for r in results)


# ---------------------------------------------------------------------------
# Quickstart smoke test — T025 (quickstart.md Step 4)
# ---------------------------------------------------------------------------

class TestQuickstartSmoke:
    def test_step4_synthetic_data_smoke(self, tmp_path):
        """Quickstart Step 4: synthetic DataFrame → valid EntrySignal, no exception (T025).

        Mirrors the quickstart.md Step 4 example verbatim, plus the assertions
        listed in the task (signal.direction not None, confidence in [0, 1]).
        """
        dates = pd.date_range("2026-01-01", periods=100, freq="1h")
        rng = np.random.default_rng(seed=42)  # fixed seed for determinism
        df_qs = pd.DataFrame({
            "time":        dates,
            "open":        rng.uniform(2300, 2400, 100),
            "high":        rng.uniform(2300, 2400, 100),
            "low":         rng.uniform(2300, 2400, 100),
            "close":       rng.uniform(2300, 2400, 100),
            "tick_volume": rng.integers(100, 1000, 100).astype(int),
        })

        with patch("src.engine.scorer.FALSE_SIGNALS_LOG", str(tmp_path / "fs.json")):
            signal = generate_signal(df_qs, htf_bias=Bias.NEUTRAL, config=TEST_CONFIG)

        assert signal is not None                   # never None (FR-022)
        assert signal.direction is not None         # always a Direction enum
        assert 0.0 <= signal.confidence <= 1.0      # invariant
        assert isinstance(signal.reason, str)
        assert len(signal.reason) > 0
