"""Integration tests for filters pipeline — 5 end-to-end tests through evaluate_filters()."""
import uuid
from datetime import datetime, timezone

import pytest

from src.filters.models import FilterResult, NewsEvent, NewsImpact
from src.filters.trade_gate import evaluate_filters


def utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


@pytest.fixture
def config(tmp_path):
    return {
        "sessions": {
            "london": {
                "local_open": "08:00", "local_close": "17:00",
                "timezone": "Europe/London", "enabled": True,
            },
            "new_york": {
                "local_open": "08:00", "local_close": "17:00",
                "timezone": "America/New_York", "enabled": True,
            },
        },
        "filters": {
            "spread": {"max_spread_usd": 0.50},
            "news": {"pre_event_minutes": 30, "post_event_minutes": 15, "impact_levels": ["HIGH"]},
            "volatility": {"atr_lookback": 14, "low_atr_ratio": 0.50, "extreme_atr_ratio": 5.0},
        },
        "logging": {"filters_log": str(tmp_path / "filter_decisions.json")},
    }


# Far-future HIGH event — never in any window for 2026-01-15 tests
_FAR_EVENT = [
    NewsEvent(
        name="Far Future Event",
        impact=NewsImpact.HIGH,
        scheduled_utc=utc(2026, 12, 31, 12, 0),
        currencies=["USD"],
    )
]

_LONDON = utc(2026, 1, 15, 10, 0)   # 10:00 UTC, winter weekday → London ALLOWED
_ASIAN = utc(2026, 1, 15, 4, 0)     # 04:00 UTC, weekday → Asian BLOCKED


def _first_blocked(result) -> str:
    """Return reason of the first BLOCKED decision."""
    return next(d.reason for d in result.decisions if d.result == FilterResult.BLOCKED)


def test_full_pipeline_allowed(config):
    """All valid inputs → TradeGateResult.final_result == ALLOWED."""
    result = evaluate_filters(
        str(uuid.uuid4()), _LONDON, 0.30, _FAR_EVENT, 14.0, 13.0, config,
    )
    assert result.final_result == FilterResult.ALLOWED
    assert all(d.result == FilterResult.ALLOWED for d in result.decisions)


def test_full_pipeline_blocked_by_session(config):
    """Asian session hour → BLOCKED with reason ASIAN_SESSION_EXCLUDED."""
    result = evaluate_filters(
        str(uuid.uuid4()), _ASIAN, 0.30, _FAR_EVENT, 14.0, 13.0, config,
    )
    assert result.final_result == FilterResult.BLOCKED
    assert _first_blocked(result) == "ASIAN_SESSION_EXCLUDED"


def test_full_pipeline_blocked_by_spread(config):
    """London session, spread=$2.00 → BLOCKED with reason SPREAD_TOO_WIDE."""
    result = evaluate_filters(
        str(uuid.uuid4()), _LONDON, 2.00, _FAR_EVENT, 14.0, 13.0, config,
    )
    assert result.final_result == FilterResult.BLOCKED
    assert _first_blocked(result) == "SPREAD_TOO_WIDE"


def test_full_pipeline_blocked_by_news(config):
    """London session, HIGH event 20 min ahead → BLOCKED with reason NEWS_BLACKOUT_PRE_EVENT."""
    near_event = NewsEvent(
        name="US NFP",
        impact=NewsImpact.HIGH,
        scheduled_utc=utc(2026, 1, 15, 10, 20),  # 20 min ahead → within 30-min window
        currencies=["USD"],
    )
    result = evaluate_filters(
        str(uuid.uuid4()), _LONDON, 0.30, [near_event], 14.0, 13.0, config,
    )
    assert result.final_result == FilterResult.BLOCKED
    assert _first_blocked(result) == "NEWS_BLACKOUT_PRE_EVENT"


def test_full_pipeline_blocked_by_volatility(config):
    """London session, ATR ratio ≈5.33 (EXTREME) → BLOCKED with reason VOLATILITY_EXTREME."""
    result = evaluate_filters(
        str(uuid.uuid4()), _LONDON, 0.30, _FAR_EVENT, 80.0, 15.0, config,
    )
    assert result.final_result == FilterResult.BLOCKED
    assert _first_blocked(result) == "VOLATILITY_EXTREME"
