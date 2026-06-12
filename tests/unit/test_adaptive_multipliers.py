"""Unit tests for src/analysis/adaptive_multipliers.py — spec006 T018."""
import pytest

from src.analysis.adaptive_multipliers import get_adaptive_multipliers
from src.analysis.models import AdaptiveMultipliers, VolatilityRegime


_CONFIG = {
    "analysis": {
        "atr": {
            "adaptive_multipliers": {
                "sl": {"LOW": 1.0, "NORMAL": 1.5, "EXTREME": 2.0},
                "tp": {"LOW": 2.0, "NORMAL": 3.0, "EXTREME": 4.0},
            }
        }
    }
}


class TestGetAdaptiveMultipliers:
    def test_low_regime_returns_correct_multipliers(self):
        m = get_adaptive_multipliers(VolatilityRegime.LOW, _CONFIG)
        assert m.sl_multiplier == pytest.approx(1.0)
        assert m.tp_multiplier == pytest.approx(2.0)
        assert m.regime == VolatilityRegime.LOW

    def test_normal_regime_returns_default_multipliers(self):
        m = get_adaptive_multipliers(VolatilityRegime.NORMAL, _CONFIG)
        assert m.sl_multiplier == pytest.approx(1.5)
        assert m.tp_multiplier == pytest.approx(3.0)
        assert m.regime == VolatilityRegime.NORMAL

    def test_extreme_regime_returns_expanded_multipliers(self):
        m = get_adaptive_multipliers(VolatilityRegime.EXTREME, _CONFIG)
        assert m.sl_multiplier == pytest.approx(2.0)
        assert m.tp_multiplier == pytest.approx(4.0)
        assert m.regime == VolatilityRegime.EXTREME

    def test_returns_adaptive_multipliers_type(self):
        result = get_adaptive_multipliers(VolatilityRegime.NORMAL, _CONFIG)
        assert isinstance(result, AdaptiveMultipliers)

    def test_regime_field_matches_input(self):
        for regime in VolatilityRegime:
            m = get_adaptive_multipliers(regime, _CONFIG)
            assert m.regime == regime

    def test_custom_config_values_respected(self):
        custom = {
            "analysis": {
                "atr": {
                    "adaptive_multipliers": {
                        "sl": {"LOW": 0.8, "NORMAL": 1.2, "EXTREME": 1.8},
                        "tp": {"LOW": 1.5, "NORMAL": 2.5, "EXTREME": 3.5},
                    }
                }
            }
        }
        m = get_adaptive_multipliers(VolatilityRegime.NORMAL, custom)
        assert m.sl_multiplier == pytest.approx(1.2)
        assert m.tp_multiplier == pytest.approx(2.5)

    def test_missing_analysis_key_raises_key_error(self):
        with pytest.raises(KeyError):
            get_adaptive_multipliers(VolatilityRegime.NORMAL, {})

    def test_missing_regime_key_raises_key_error(self):
        bad_config = {
            "analysis": {
                "atr": {
                    "adaptive_multipliers": {
                        "sl": {"LOW": 1.0},   # NORMAL and EXTREME missing
                        "tp": {"LOW": 2.0},
                    }
                }
            }
        }
        with pytest.raises(KeyError):
            get_adaptive_multipliers(VolatilityRegime.NORMAL, bad_config)
