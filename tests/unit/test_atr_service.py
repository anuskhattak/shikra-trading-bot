"""Unit tests for src/analysis/atr_service.py — spec006 T023, T026, T027."""
from datetime import datetime, timezone

import pytest

from src.analysis.atr_service import ATRService
from src.analysis.models import AdaptiveMultipliers, OHLCVBar, Timeframe, VolatilityRegime


_TS = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

_CONFIG = {
    "analysis": {
        "atr": {
            "period": 14,
            "reference_period": 20,
            "adaptive_multipliers": {
                "sl": {"LOW": 1.0, "NORMAL": 1.5, "EXTREME": 2.0},
                "tp": {"LOW": 2.0, "NORMAL": 3.0, "EXTREME": 4.0},
            },
        }
    },
    "filters": {
        "volatility": {
            "atr_lookback": 14,
            "low_atr_ratio": 0.7,
            "extreme_atr_ratio": 2.0,
        }
    },
}


def _make_bars(n: int, close_start: float = 2000.0) -> list[OHLCVBar]:
    """Create n valid OHLCVBar instances with realistic spread."""
    bars = []
    close = close_start
    for i in range(n):
        high  = close + 8.0
        low   = close - 8.0
        bars.append(OHLCVBar(open=close - 1, high=high, low=low, close=close, volume=100.0, timestamp=_TS))
        close += 0.5
    return bars


# ─── __init__ ───────────────────────────────────────────────────────────────

class TestATRServiceInit:
    def test_valid_config_creates_service(self):
        svc = ATRService(_CONFIG)
        assert svc is not None

    def test_missing_analysis_key_raises(self):
        with pytest.raises(KeyError):
            ATRService({})

    def test_missing_atr_key_raises(self):
        with pytest.raises(KeyError):
            ATRService({"analysis": {}})


# ─── empty cache getters ─────────────────────────────────────────────────────

class TestEmptyCache:
    def setup_method(self):
        self.svc = ATRService(_CONFIG)

    def test_get_atr_returns_none_on_empty_cache(self):
        for tf in Timeframe:
            assert self.svc.get_atr(tf) is None

    def test_get_h1_readings_returns_none_tuple(self):
        assert self.svc.get_h1_readings() == (None, None)

    def test_get_d1_atr_returns_none(self):
        assert self.svc.get_d1_atr() is None

    def test_is_ready_false_on_empty(self):
        for tf in Timeframe:
            assert self.svc.is_ready(tf) is False


# ─── refresh ────────────────────────────────────────────────────────────────

class TestRefresh:
    def setup_method(self):
        self.svc = ATRService(_CONFIG)

    def test_refresh_with_sufficient_bars_returns_reading(self):
        bars = _make_bars(20)
        reading = self.svc.refresh(Timeframe.H1, bars)
        assert reading.current_atr is not None
        assert reading.current_atr > 0

    def test_refresh_populates_cache_and_sets_is_fresh(self):
        self.svc.refresh(Timeframe.H1, _make_bars(20))
        assert self.svc.is_ready(Timeframe.H1)
        assert self.svc._cache[Timeframe.H1].is_fresh is True  # type: ignore[union-attr]

    def test_refresh_with_few_bars_returns_none_atr(self):
        bars = _make_bars(5)
        reading = self.svc.refresh(Timeframe.H1, bars)
        assert reading.current_atr is None

    def test_repeated_get_atr_returns_same_cached_value(self):
        """SC-002: no recomputation between bar closes."""
        self.svc.refresh(Timeframe.H1, _make_bars(20))
        v1 = self.svc.get_atr(Timeframe.H1)
        v2 = self.svc.get_atr(Timeframe.H1)
        v3 = self.svc.get_atr(Timeframe.H1)
        assert v1 == v2 == v3

    def test_reference_atr_available_after_enough_refreshes(self):
        """Need 20 ATR values → 20 refreshes with sufficient bars each."""
        for _ in range(20):
            self.svc.refresh(Timeframe.H1, _make_bars(15))
        _, ref = self.svc.get_h1_readings()
        assert ref is not None

    def test_never_raises_on_empty_bars(self):
        reading = self.svc.refresh(Timeframe.H1, [])
        assert reading.current_atr is None

    def test_never_raises_on_all_invalid_bars(self):
        bad_bars = [OHLCVBar(open=1900, high=1890, low=1895, close=1892, volume=0, timestamp=_TS)] * 20
        reading = self.svc.refresh(Timeframe.H1, bad_bars)
        assert reading.current_atr is None


# ─── mark_stale ─────────────────────────────────────────────────────────────

class TestMarkStale:
    def setup_method(self):
        self.svc = ATRService(_CONFIG)

    def test_mark_stale_sets_is_fresh_false(self):
        self.svc.refresh(Timeframe.H1, _make_bars(20))
        self.svc.mark_stale(Timeframe.H1)
        assert self.svc._cache[Timeframe.H1].is_fresh is False  # type: ignore[union-attr]

    def test_mark_stale_on_empty_cache_does_not_raise(self):
        self.svc.mark_stale(Timeframe.H1)   # no cache yet — should be safe


# ─── stale fallback ──────────────────────────────────────────────────────────

class TestStaleFallback:
    def test_refresh_failure_preserves_last_value_and_marks_stale(self, monkeypatch):
        """FR-011: stale fallback on refresh failure."""
        svc = ATRService(_CONFIG)
        svc.refresh(Timeframe.H1, _make_bars(20))
        first_atr = svc.get_atr(Timeframe.H1)
        assert first_atr is not None

        # Force validate_ohlcv_bars to raise unexpectedly
        import src.analysis.atr_service as mod
        monkeypatch.setattr(mod, "validate_ohlcv_bars", lambda bars: (_ for _ in ()).throw(RuntimeError("simulated failure")))

        reading = svc.refresh(Timeframe.H1, _make_bars(20))
        # Should return last cached value
        assert reading.current_atr == pytest.approx(first_atr)
        assert svc._cache[Timeframe.H1].is_fresh is False  # type: ignore[union-attr]


# ─── is_ready ───────────────────────────────────────────────────────────────

class TestIsReady:
    def setup_method(self):
        self.svc = ATRService(_CONFIG)

    def test_is_ready_false_before_refresh(self):
        assert self.svc.is_ready(Timeframe.D1) is False

    def test_is_ready_true_after_successful_refresh(self):
        self.svc.refresh(Timeframe.D1, _make_bars(20))
        assert self.svc.is_ready(Timeframe.D1) is True

    def test_is_ready_false_after_refresh_with_insufficient_bars(self):
        self.svc.refresh(Timeframe.D1, _make_bars(5))
        assert self.svc.is_ready(Timeframe.D1) is False


# ─── get_h1_readings ─────────────────────────────────────────────────────────

class TestGetH1Readings:
    def setup_method(self):
        self.svc = ATRService(_CONFIG)

    def test_returns_none_tuple_before_refresh(self):
        assert self.svc.get_h1_readings() == (None, None)

    def test_returns_current_atr_after_first_refresh(self):
        self.svc.refresh(Timeframe.H1, _make_bars(20))
        current, _ = self.svc.get_h1_readings()
        assert current is not None and current > 0

    def test_h1_does_not_return_d1_values(self):
        self.svc.refresh(Timeframe.D1, _make_bars(20, close_start=3000.0))
        assert self.svc.get_h1_readings() == (None, None)


# ─── get_adaptive_multipliers ────────────────────────────────────────────────

class TestGetAdaptiveMultipliers:
    def setup_method(self):
        self.svc = ATRService(_CONFIG)

    def test_returns_adaptive_multipliers_type(self):
        m = self.svc.get_adaptive_multipliers(VolatilityRegime.NORMAL)
        assert isinstance(m, AdaptiveMultipliers)

    def test_normal_regime_multipliers(self):
        m = self.svc.get_adaptive_multipliers(VolatilityRegime.NORMAL)
        assert m.sl_multiplier == pytest.approx(1.5)
        assert m.tp_multiplier == pytest.approx(3.0)

    def test_extreme_regime_widens_stop(self):
        m = self.svc.get_adaptive_multipliers(VolatilityRegime.EXTREME)
        assert m.sl_multiplier > self.svc.get_adaptive_multipliers(VolatilityRegime.NORMAL).sl_multiplier


# ─── integration smoke tests (T026, T027) ────────────────────────────────────

class TestIntegrationSmoke:
    def test_t026_h1_readings_feed_volatility_filter(self):
        """T026: get_h1_readings() output types are compatible with volatility_filter."""
        from src.filters.volatility_filter import check_volatility
        svc = ATRService(_CONFIG)
        # Build enough history so reference_atr is also available
        for _ in range(20):
            svc.refresh(Timeframe.H1, _make_bars(15))

        current, reference = svc.get_h1_readings()
        assert current is not None and reference is not None
        decision = check_volatility(current, reference, _CONFIG)
        assert decision.filter_name == "volatility"

    def test_t027_d1_atr_feeds_lot_calculator(self):
        """T027: get_d1_atr() and get_adaptive_multipliers() feed lot_calculator."""
        from src.engine.models import Direction
        from src.risk.lot_calculator import calculate_sl_price

        svc = ATRService(_CONFIG)
        svc.refresh(Timeframe.D1, _make_bars(20, close_start=2350.0))
        d1_atr = svc.get_d1_atr()
        assert d1_atr is not None

        multipliers = svc.get_adaptive_multipliers(VolatilityRegime.NORMAL)
        sl = calculate_sl_price(
            entry=2350.0,
            direction=Direction.LONG,
            d1_atr=d1_atr,
            sl_atr_multiplier=multipliers.sl_multiplier,
        )
        assert sl < 2350.0   # SL below entry for LONG
