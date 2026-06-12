"""Unit tests for src/analysis/reference_atr.py — spec006 T016."""
import pytest

from src.analysis.reference_atr import compute_reference_atr


class TestComputeReferenceAtr:
    def test_correct_rolling_average_from_20_values(self):
        history = [float(i) for i in range(1, 21)]   # 1..20
        expected = sum(range(1, 21)) / 20             # = 10.5
        assert compute_reference_atr(history, period=20) == pytest.approx(expected)

    def test_uses_last_n_values_not_all(self):
        # 25 values: first 5 are large outliers, last 20 are small
        outliers = [1000.0] * 5
        recent   = [10.0]   * 20
        history  = outliers + recent
        result   = compute_reference_atr(history, period=20)
        assert result == pytest.approx(10.0)

    def test_returns_none_when_fewer_than_period(self):
        assert compute_reference_atr([5.0] * 19, period=20) is None

    def test_returns_none_on_empty(self):
        assert compute_reference_atr([], period=20) is None

    def test_determinism_sc007(self):
        history = [float(i) * 0.5 for i in range(20)]
        r1 = compute_reference_atr(history, period=20)
        r2 = compute_reference_atr(history, period=20)
        assert r1 == r2

    def test_all_same_values(self):
        history = [5.0] * 20
        assert compute_reference_atr(history, period=20) == pytest.approx(5.0)

    def test_ratio_one_when_current_equals_reference(self):
        """SC-007 + US2 S2: current == reference → ratio = 1.0 (NORMAL regime)."""
        history = [10.0] * 20
        reference = compute_reference_atr(history, period=20)
        current = 10.0
        assert reference is not None
        ratio = current / reference
        assert ratio == pytest.approx(1.0)

    def test_ratio_two_triggers_extreme(self):
        """US2 S3: current = 2× reference → ratio = 2.0 (EXTREME boundary)."""
        history = [10.0] * 20
        reference = compute_reference_atr(history, period=20)
        current = 20.0
        assert reference is not None
        ratio = current / reference
        assert ratio == pytest.approx(2.0)

    def test_exactly_period_values_returns_value(self):
        history = [7.5] * 20
        assert compute_reference_atr(history, period=20) == pytest.approx(7.5)
