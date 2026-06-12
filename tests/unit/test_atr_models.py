"""Unit tests for src/analysis/models.py — spec006 T010."""
from datetime import datetime, timezone

import pytest

from src.analysis.models import (
    AdaptiveMultipliers,
    ATRCache,
    ATRReading,
    OHLCVBar,
    Timeframe,
    VolatilityRegime,
)


_TS = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


class TestTimeframe:
    def test_mt5_constant_values(self):
        assert Timeframe.M5.value  == 5
        assert Timeframe.H1.value  == 16385
        assert Timeframe.H4.value  == 16388
        assert Timeframe.D1.value  == 16408

    def test_all_four_members_exist(self):
        names = {tf.name for tf in Timeframe}
        assert names == {"M5", "H1", "H4", "D1"}


class TestOHLCVBar:
    def test_instantiation(self):
        bar = OHLCVBar(open=1900.0, high=1905.0, low=1895.0, close=1902.0, volume=500.0, timestamp=_TS)
        assert bar.high == 1905.0

    def test_frozen(self):
        bar = OHLCVBar(open=1900.0, high=1905.0, low=1895.0, close=1902.0, volume=500.0, timestamp=_TS)
        with pytest.raises((AttributeError, TypeError)):
            bar.close = 9999.0  # type: ignore[misc]


class TestVolatilityRegime:
    def test_members(self):
        assert VolatilityRegime.LOW.value     == "LOW"
        assert VolatilityRegime.NORMAL.value  == "NORMAL"
        assert VolatilityRegime.EXTREME.value == "EXTREME"

    def test_imported_from_filters_is_same_class(self):
        from src.filters.models import VolatilityRegime as FiltersVR
        assert FiltersVR is VolatilityRegime


class TestAdaptiveMultipliers:
    def test_instantiation(self):
        m = AdaptiveMultipliers(sl_multiplier=1.5, tp_multiplier=3.0, regime=VolatilityRegime.NORMAL)
        assert m.sl_multiplier == 1.5
        assert m.tp_multiplier == 3.0
        assert m.regime == VolatilityRegime.NORMAL

    def test_frozen(self):
        m = AdaptiveMultipliers(sl_multiplier=1.5, tp_multiplier=3.0, regime=VolatilityRegime.NORMAL)
        with pytest.raises((AttributeError, TypeError)):
            m.sl_multiplier = 9.0  # type: ignore[misc]


class TestATRReading:
    def test_full_instantiation(self):
        r = ATRReading(
            timeframe=Timeframe.H1,
            current_atr=10.5,
            reference_atr=9.8,
            ratio=10.5 / 9.8,
            bar_count=20,
            timestamp=_TS,
        )
        assert r.current_atr == 10.5
        assert r.bar_count == 20

    def test_accepts_none_for_optional_fields(self):
        r = ATRReading(
            timeframe=Timeframe.D1,
            current_atr=None,
            reference_atr=None,
            ratio=None,
            bar_count=0,
            timestamp=_TS,
        )
        assert r.current_atr is None
        assert r.ratio is None


class TestATRCache:
    def test_instantiation(self):
        reading = ATRReading(
            timeframe=Timeframe.H1,
            current_atr=10.0,
            reference_atr=9.5,
            ratio=10.0 / 9.5,
            bar_count=15,
            timestamp=_TS,
        )
        cache = ATRCache(reading=reading, is_fresh=True, last_refreshed=_TS)
        assert cache.is_fresh is True

    def test_is_fresh_mutable(self):
        reading = ATRReading(
            timeframe=Timeframe.H1,
            current_atr=10.0,
            reference_atr=None,
            ratio=None,
            bar_count=14,
            timestamp=_TS,
        )
        cache = ATRCache(reading=reading, is_fresh=True, last_refreshed=_TS)
        cache.is_fresh = False
        assert cache.is_fresh is False
