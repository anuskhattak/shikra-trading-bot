"""Unit tests for src/analysis/atr_calculator.py — spec006 T014."""
from datetime import datetime, timezone

import pytest

from src.analysis.atr_calculator import compute_atr, compute_true_range, validate_ohlcv_bars
from src.analysis.models import OHLCVBar


_TS = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _bar(high: float, low: float, close: float, open_: float = 0.0) -> OHLCVBar:
    """Helper: create a minimal OHLCVBar."""
    return OHLCVBar(open=open_ or low, high=high, low=low, close=close, volume=100.0, timestamp=_TS)


# ─── validate_ohlcv_bars ────────────────────────────────────────────────────

class TestValidateOhlcvBars:
    def test_valid_bars_pass_through(self):
        bars = [_bar(high=1905, low=1895, close=1902)]
        assert validate_ohlcv_bars(bars) == bars

    def test_rejects_high_less_than_low(self):
        bad = _bar(high=1890, low=1895, close=1892)   # high < low
        result = validate_ohlcv_bars([bad])
        assert result == []

    def test_rejects_close_zero(self):
        bad = _bar(high=1905, low=1895, close=0.0)
        assert validate_ohlcv_bars([bad]) == []

    def test_rejects_close_negative(self):
        bad = _bar(high=1905, low=1895, close=-1.0)
        assert validate_ohlcv_bars([bad]) == []

    def test_mixed_bars_keeps_valid_only(self):
        good = _bar(high=1905, low=1895, close=1900)
        bad  = _bar(high=1890, low=1895, close=1892)
        assert validate_ohlcv_bars([good, bad]) == [good]

    def test_empty_input_returns_empty(self):
        assert validate_ohlcv_bars([]) == []

    def test_all_invalid_returns_empty(self):
        bars = [_bar(high=1890, low=1895, close=1892)] * 5
        assert validate_ohlcv_bars(bars) == []

    def test_never_raises(self):
        # Even with bizarre data, should not raise
        result = validate_ohlcv_bars([_bar(high=0, low=0, close=0)])
        assert isinstance(result, list)


# ─── compute_true_range ─────────────────────────────────────────────────────

class TestComputeTrueRange:
    def test_hand_calculated_3_bars(self):
        """
        Bar0: close=1900
        Bar1: high=1905, low=1895 → TR = max(10, |1905-1900|, |1895-1900|) = max(10,5,5) = 10
        Bar2: high=1910, low=1898 → TR = max(12, |1910-1902|, |1898-1902|) = max(12,8,4) = 12
        where bar1.close = 1902 (prev_close for bar2)
        """
        bars = [
            _bar(high=1901, low=1899, close=1900),
            _bar(high=1905, low=1895, close=1902),
            _bar(high=1910, low=1898, close=1906),
        ]
        tr = compute_true_range(bars)
        assert len(tr) == 2
        assert tr[0] == pytest.approx(10.0, abs=1e-9)
        assert tr[1] == pytest.approx(12.0, abs=1e-9)

    def test_result_length_is_bars_minus_1(self):
        bars = [_bar(1905, 1895, 1900)] * 5
        assert len(compute_true_range(bars)) == 4

    def test_raises_on_single_bar(self):
        with pytest.raises(ValueError):
            compute_true_range([_bar(1905, 1895, 1900)])

    def test_raises_on_empty(self):
        with pytest.raises(ValueError):
            compute_true_range([])

    def test_tr_never_negative(self):
        bars = [_bar(high=1905 + i, low=1895 + i, close=1900 + i) for i in range(10)]
        tr = compute_true_range(bars)
        assert all(v >= 0 for v in tr)


# ─── compute_atr ────────────────────────────────────────────────────────────

class TestComputeAtr:
    def _make_bars(self, n: int, base_close: float = 1900.0, spread: float = 5.0) -> list[OHLCVBar]:
        """Create n bars with deterministic, valid OHLCV data."""
        bars = []
        close = base_close
        for i in range(n):
            high  = close + spread
            low   = close - spread
            bars.append(_bar(high=high, low=low, close=close, open_=close - 1))
            close += 0.1   # tiny drift to avoid flat ATR edge cases
        return bars

    def test_returns_none_when_bars_less_than_period_plus_1(self):
        bars = self._make_bars(14)   # need 15 for period=14
        assert compute_atr(bars, period=14) is None

    def test_returns_none_on_exactly_period_bars(self):
        bars = self._make_bars(14)
        assert compute_atr(bars, period=14) is None

    def test_returns_value_for_period_plus_1_bars(self):
        bars = self._make_bars(15)
        result = compute_atr(bars, period=14)
        assert result is not None
        assert result > 0

    def test_accuracy_within_0_1_percent(self):
        """Hand-validate ATR for 3 deterministic bars, period=2."""
        bars = [
            _bar(high=1901, low=1899, close=1900),
            _bar(high=1905, low=1895, close=1902),  # TR = 10
            _bar(high=1910, low=1898, close=1906),  # TR = 12 (prev_close=1902)
        ]
        # period=2, ATR = (10 + 12) / 2 = 11.0
        result = compute_atr(bars, period=2)
        assert result == pytest.approx(11.0, rel=0.001)   # ±0.1%

    def test_xauusd_realistic_14_bar_atr(self):
        """ATR for 15 bars at realistic XAUUSD spread; verify positive and in range."""
        bars = self._make_bars(15, base_close=2350.0, spread=8.0)
        result = compute_atr(bars, period=14)
        assert result is not None
        # Spread = 8, so each TR ≈ 16 (high-low); ATR should be near 16
        assert 10.0 < result < 25.0

    def test_returns_none_on_all_invalid_bars(self):
        bad_bars = [_bar(high=1890, low=1895, close=1892)] * 20
        # validate_ohlcv_bars called by service; compute_atr gets empty after filtering
        # but compute_atr itself just checks len — passing pre-validated empty list
        assert compute_atr([], period=14) is None

    def test_none_not_zero_on_insufficient_data(self):
        """SC-005: must return None, not 0.0, to prevent division-by-zero in lot_calculator."""
        result = compute_atr(self._make_bars(5), period=14)
        assert result is None
        assert result != 0.0
