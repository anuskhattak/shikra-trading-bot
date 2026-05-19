"""Unit tests for news_filter — 9 tests covering blackout windows, fail-safe, calendar load."""
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.filters.models import FilterResult, NewsEvent, NewsImpact
from src.filters.news_filter import check_news, load_news_calendar


def utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


@pytest.fixture
def config():
    return {
        "filters": {
            "news": {
                "pre_event_minutes": 30,
                "post_event_minutes": 15,
                "impact_levels": ["HIGH"],
            }
        }
    }


@pytest.fixture
def nfp_event():
    """NFP scheduled at 2026-06-06 12:30 UTC."""
    return NewsEvent(
        name="US Non-Farm Payrolls",
        impact=NewsImpact.HIGH,
        scheduled_utc=utc(2026, 6, 6, 12, 30),
        currencies=["USD", "XAU"],
    )


# --- Pre-event blackout ---

def test_pre_event_window_blocked(config, nfp_event):
    """Signal 25 min before NFP → within 30-min pre-event window → BLOCKED."""
    now = utc(2026, 6, 6, 12, 5)
    decision = check_news(now, [nfp_event], config)
    assert decision.result == FilterResult.BLOCKED
    assert decision.reason == "NEWS_BLACKOUT_PRE_EVENT"


# --- Post-event blackout ---

def test_post_event_window_blocked(config, nfp_event):
    """Signal 15 min after NFP → within 15-min post-event window → BLOCKED."""
    now = utc(2026, 6, 6, 12, 45)
    decision = check_news(now, [nfp_event], config)
    assert decision.result == FilterResult.BLOCKED
    assert decision.reason == "NEWS_BLACKOUT_POST_EVENT"


# --- Allowed ---

def test_no_event_in_window_allowed(config, nfp_event):
    """HIGH event exists but signal is 2.5h before → outside all windows → ALLOWED."""
    now = utc(2026, 6, 6, 10, 0)
    decision = check_news(now, [nfp_event], config)
    assert decision.result == FilterResult.ALLOWED


def test_outside_both_windows_allowed(config, nfp_event):
    """Signal 45 min before event → outside 30-min pre-event window → ALLOWED."""
    now = utc(2026, 6, 6, 11, 45)
    decision = check_news(now, [nfp_event], config)
    assert decision.result == FilterResult.ALLOWED


# --- Fail-safe ---

def test_empty_calendar_blocked(config):
    """Empty events list → fail-safe → NEWS_CALENDAR_UNAVAILABLE BLOCKED."""
    now = utc(2026, 6, 6, 10, 0)
    decision = check_news(now, [], config)
    assert decision.result == FilterResult.BLOCKED
    assert decision.reason == "NEWS_CALENDAR_UNAVAILABLE"


# --- Impact filtering ---

def test_medium_impact_event_ignored(config):
    """MEDIUM event in blackout window → ignored (only HIGH triggers) → ALLOWED."""
    medium_event = NewsEvent(
        name="Some Medium Event",
        impact=NewsImpact.MEDIUM,
        scheduled_utc=utc(2026, 6, 6, 12, 30),
        currencies=["USD"],
    )
    now = utc(2026, 6, 6, 12, 5)  # 25 min before — would block if HIGH
    decision = check_news(now, [medium_event], config)
    assert decision.result == FilterResult.ALLOWED


# --- Calendar loading ---

def test_load_calendar_valid_json():
    """load_news_calendar returns list[NewsEvent] for valid JSON file."""
    events = load_news_calendar("data/news_calendar.json")
    assert isinstance(events, list)
    assert len(events) > 0
    assert all(isinstance(e, NewsEvent) for e in events)


def test_load_calendar_file_missing_returns_empty():
    """Non-existent path → fail-safe → returns empty list."""
    events = load_news_calendar("data/does_not_exist_xyz.json")
    assert events == []


def test_load_calendar_invalid_json_returns_empty(tmp_path):
    """Malformed JSON file → fail-safe → returns empty list."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not valid json !!!}")
    events = load_news_calendar(str(bad_file))
    assert events == []
