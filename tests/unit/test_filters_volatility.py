"""Unit tests for volatility_filter — 10 tests covering LOW/NORMAL/EXTREME boundaries and classify_regime."""
import pytest

from src.filters.models import FilterResult, VolatilityRegime, VolatilityReading
from src.filters.volatility_filter import check_volatility, classify_regime


@pytest.fixture
def config():
    return {
        "filters": {
            "volatility": {
                "atr_lookback": 14,
                "low_atr_ratio": 0.50,
                "extreme_atr_ratio": 5.0,
            }
        }
    }


# --- check_volatility: BLOCKED cases ---

def test_low_regime_blocked(config):
    """current_atr=5, ref=15, ratio=0.33 → LOW → VOLATILITY_TOO_LOW BLOCKED."""
    decision = check_volatility(5.0, 15.0, config)
    assert decision.result == FilterResult.BLOCKED
    assert decision.reason == "VOLATILITY_TOO_LOW"


def test_extreme_regime_blocked(config):
    """current_atr=80, ref=15, ratio≈5.33 → EXTREME → VOLATILITY_EXTREME BLOCKED."""
    decision = check_volatility(80.0, 15.0, config)
    assert decision.result == FilterResult.BLOCKED
    assert decision.reason == "VOLATILITY_EXTREME"


# --- check_volatility: ALLOWED case ---

def test_normal_regime_allowed(config):
    """current_atr=14, ref=13, ratio≈1.07 → NORMAL → ALLOWED."""
    decision = check_volatility(14.0, 13.0, config)
    assert decision.result == FilterResult.ALLOWED


# --- Boundary conditions ---

def test_extreme_boundary_at_5x(config):
    """ratio=5.0 exactly → EXTREME (>= threshold)."""
    reading = classify_regime(5.0, 1.0, config)
    assert reading.regime == VolatilityRegime.EXTREME


def test_low_boundary_at_0_5x(config):
    """ratio=0.5 exactly → NORMAL (not LOW — low_atr_ratio is exclusive lower bound)."""
    reading = classify_regime(0.5, 1.0, config)
    assert reading.regime == VolatilityRegime.NORMAL


# --- classify_regime: regime values ---

def test_classify_low(config):
    """ratio=0.3 (< 0.5) → LOW regime."""
    reading = classify_regime(0.3, 1.0, config)
    assert reading.regime == VolatilityRegime.LOW


def test_classify_normal(config):
    """ratio=1.5 (in [0.5, 5.0)) → NORMAL regime."""
    reading = classify_regime(1.5, 1.0, config)
    assert reading.regime == VolatilityRegime.NORMAL


def test_classify_extreme(config):
    """ratio=6.0 (>= 5.0) → EXTREME regime."""
    reading = classify_regime(6.0, 1.0, config)
    assert reading.regime == VolatilityRegime.EXTREME


# --- metric_value is ATR ratio float ---

def test_metric_value_is_ratio(config):
    """FilterDecision.metric_value must be ATR ratio float, not regime string."""
    decision = check_volatility(5.0, 15.0, config)
    expected_ratio = 5.0 / 15.0
    assert isinstance(decision.metric_value, float)
    assert abs(decision.metric_value - expected_ratio) < 1e-9


# --- classify_regime returns full VolatilityReading ---

def test_classify_regime_returns_volatility_reading(config):
    """classify_regime() returns VolatilityReading with all 5 fields populated."""
    reading = classify_regime(14.0, 13.0, config)
    assert isinstance(reading, VolatilityReading)
    assert reading.regime is not None
    assert reading.current_atr == 14.0
    assert reading.reference_atr == 13.0
    assert abs(reading.ratio - 14.0 / 13.0) < 1e-9
    assert reading.timestamp is not None
