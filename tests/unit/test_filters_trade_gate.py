"""Unit tests for trade_gate — 8 tests covering orchestration, short-circuit, error path, timing."""
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.filters.models import FilterResult, NewsEvent, NewsImpact
from src.filters.trade_gate import evaluate_filters


def utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# 10:00 UTC, winter weekday → London session ALLOWED
LONDON_SESSION = utc(2026, 1, 15, 10, 0)
# 04:00 UTC, weekday → Asian session BLOCKED
ASIAN_SESSION = utc(2026, 1, 15, 4, 0)

GOOD_SPREAD = 0.30
BAD_SPREAD = 2.00
NORMAL_ATR = (14.0, 13.0)   # ratio ≈ 1.07 → NORMAL → ALLOWED
EXTREME_ATR = (80.0, 15.0)  # ratio ≈ 5.33 → EXTREME → BLOCKED

# Far-future HIGH event — not in any blackout window on 2026-01-15
FAR_EVENT = [
    NewsEvent(
        name="Far Future NFP",
        impact=NewsImpact.HIGH,
        scheduled_utc=utc(2026, 6, 6, 12, 30),
        currencies=["USD"],
    )
]


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


# --- Core orchestration ---

def test_all_filters_pass_returns_allowed(config):
    """All 4 filters pass → ALLOWED, 4 decisions in result."""
    result = evaluate_filters(
        str(uuid.uuid4()), LONDON_SESSION, GOOD_SPREAD,
        FAR_EVENT, *NORMAL_ATR, config,
    )
    assert result.final_result == FilterResult.ALLOWED
    assert len(result.decisions) == 4


def test_session_block_short_circuits(config):
    """Asian session → session BLOCKED → only 1 decision evaluated."""
    result = evaluate_filters(
        str(uuid.uuid4()), ASIAN_SESSION, GOOD_SPREAD,
        FAR_EVENT, *NORMAL_ATR, config,
    )
    assert result.final_result == FilterResult.BLOCKED
    assert len(result.decisions) == 1


def test_spread_block_after_session_pass(config):
    """Session ALLOWED, spread=$2.00 → spread BLOCKED → exactly 2 decisions."""
    result = evaluate_filters(
        str(uuid.uuid4()), LONDON_SESSION, BAD_SPREAD,
        FAR_EVENT, *NORMAL_ATR, config,
    )
    assert result.final_result == FilterResult.BLOCKED
    assert len(result.decisions) == 2


def test_news_block_produces_3_decisions(config):
    """Session + spread ALLOWED, news event 20 min ahead → news BLOCKED → 3 decisions."""
    near_event = NewsEvent(
        name="Near NFP",
        impact=NewsImpact.HIGH,
        scheduled_utc=utc(2026, 1, 15, 10, 20),  # 20 min ahead of LONDON_SESSION
        currencies=["USD"],
    )
    result = evaluate_filters(
        str(uuid.uuid4()), LONDON_SESSION, GOOD_SPREAD,
        [near_event], *NORMAL_ATR, config,
    )
    assert result.final_result == FilterResult.BLOCKED
    assert len(result.decisions) == 3


# --- Field completeness ---

def test_each_decision_has_correct_fields(config):
    """Every FilterDecision in result has all 5 required fields populated."""
    result = evaluate_filters(
        str(uuid.uuid4()), LONDON_SESSION, GOOD_SPREAD,
        FAR_EVENT, *NORMAL_ATR, config,
    )
    for d in result.decisions:
        assert d.filter_name in {"session", "spread", "news", "volatility"}
        assert isinstance(d.result, FilterResult)
        assert isinstance(d.reason, str) and d.reason
        assert d.metric_value is not None
        assert d.timestamp is not None


# --- Exception fail-safe ---

def test_filter_exception_produces_filter_error(config):
    """If session filter raises, result is BLOCKED with reason FILTER_ERROR."""
    with patch("src.filters.trade_gate.check_session", side_effect=RuntimeError("boom")):
        result = evaluate_filters(
            str(uuid.uuid4()), LONDON_SESSION, GOOD_SPREAD,
            FAR_EVENT, *NORMAL_ATR, config,
        )
    assert result.final_result == FilterResult.BLOCKED
    assert result.decisions[0].filter_name == "session"
    assert result.decisions[0].reason == "FILTER_ERROR"


# --- Signal ID ---

def test_trade_gate_result_signal_id_preserved(config):
    """signal_id passed in is preserved in TradeGateResult."""
    sid = str(uuid.uuid4())
    result = evaluate_filters(sid, LONDON_SESSION, GOOD_SPREAD, FAR_EVENT, *NORMAL_ATR, config)
    assert result.signal_id == sid


# --- SC-001: Timing ---

def test_evaluate_filters_completes_within_100ms(config):
    """evaluate_filters() must complete in under 100ms (SC-001)."""
    t0 = time.perf_counter()
    evaluate_filters(
        str(uuid.uuid4()), LONDON_SESSION, GOOD_SPREAD,
        FAR_EVENT, *NORMAL_ATR, config,
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.1, f"evaluate_filters took {elapsed:.3f}s — exceeds 100ms limit (SC-001)"
