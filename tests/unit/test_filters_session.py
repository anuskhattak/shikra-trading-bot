"""Unit tests for session_filter — 11 tests covering DST, holidays, boundaries, sessions."""
from datetime import datetime, timezone

import pytest

from src.filters.models import FilterResult, SessionLabel
from src.filters.session_filter import check_session, get_current_session


@pytest.fixture
def config():
    return {
        "sessions": {
            "london": {
                "local_open": "08:00",
                "local_close": "17:00",
                "timezone": "Europe/London",
                "enabled": True,
            },
            "new_york": {
                "local_open": "08:00",
                "local_close": "17:00",
                "timezone": "America/New_York",
                "enabled": True,
            },
        }
    }


def utc(year, month, day, hour, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


# --- Allowed trading sessions ---

def test_london_ny_overlap_allowed(config):
    # Thu 2026-01-15 13:30 UTC: London=13:30 GMT (open), NY=08:30 EST (open) → OVERLAP
    decision = check_session(utc(2026, 1, 15, 13, 30), config)
    assert decision.result == FilterResult.ALLOWED
    assert decision.metric_value == SessionLabel.LONDON_NY_OVERLAP.value


def test_london_session_allowed(config):
    # Thu 2026-01-15 09:00 UTC: London=09:00 GMT (open), NY=04:00 EST (closed) → LONDON
    decision = check_session(utc(2026, 1, 15, 9, 0), config)
    assert decision.result == FilterResult.ALLOWED
    assert decision.metric_value == SessionLabel.LONDON.value


def test_asian_session_blocked(config):
    # Thu 2026-01-15 04:00 UTC → ASIAN, BLOCKED with ASIAN_SESSION_EXCLUDED
    decision = check_session(utc(2026, 1, 15, 4, 0), config)
    assert decision.result == FilterResult.BLOCKED
    assert decision.reason == "ASIAN_SESSION_EXCLUDED"


# --- Market closed ---

def test_saturday_blocked(config):
    # 2026-01-17 is Saturday
    decision = check_session(utc(2026, 1, 17, 12, 0), config)
    assert decision.result == FilterResult.BLOCKED
    assert decision.reason == "MARKET_CLOSED"


def test_sunday_blocked(config):
    # 2026-01-18 is Sunday
    decision = check_session(utc(2026, 1, 18, 12, 0), config)
    assert decision.result == FilterResult.BLOCKED
    assert decision.reason == "MARKET_CLOSED"


def test_post_ny_gap_closed(config):
    # Thu 2026-01-15 22:00 UTC: NY closed (17:00 EST), London closed → post-NY gap
    decision = check_session(utc(2026, 1, 15, 22, 0), config)
    assert decision.result == FilterResult.BLOCKED
    assert decision.reason == "MARKET_CLOSED"


def test_holiday_christmas_blocked(config):
    # 2026-12-25 Friday — Christmas Day (GB public holiday)
    decision = check_session(utc(2026, 12, 25, 10, 0), config)
    assert decision.result == FilterResult.BLOCKED
    assert decision.reason == "MARKET_CLOSED"


def test_holiday_good_friday_blocked(config):
    # 2026-04-03 Good Friday (Easter Sunday = 2026-04-05)
    decision = check_session(utc(2026, 4, 3, 10, 0), config)
    assert decision.result == FilterResult.BLOCKED
    assert decision.reason == "MARKET_CLOSED"


# --- Session boundary: inclusive start, exclusive end [open, close) ---

def test_session_boundary_exclusive_end(config):
    # Summer 2026-07-16 16:00:00 UTC: London=17:00:00 BST (exactly at close → NOT open)
    # NY=12:00:00 EDT (open) → result must not be LONDON or LONDON_NY_OVERLAP
    label = get_current_session(utc(2026, 7, 16, 16, 0, 0), config)
    assert label not in (SessionLabel.LONDON, SessionLabel.LONDON_NY_OVERLAP)


# --- DST transition tests ---

def test_dst_london_summer_shifts_window(config):
    # BST (UTC+1): London opens at 07:00 UTC in summer (08:00 BST)
    label_summer = get_current_session(utc(2026, 7, 16, 7, 30), config)
    assert label_summer in (SessionLabel.LONDON, SessionLabel.LONDON_NY_OVERLAP)

    # GMT (UTC+0): 07:30 UTC in winter = 07:30 GMT → London NOT yet open (opens 08:00)
    label_winter = get_current_session(utc(2026, 1, 15, 7, 30), config)
    assert label_winter not in (SessionLabel.LONDON, SessionLabel.LONDON_NY_OVERLAP)


def test_dst_ny_summer_shifts_window(config):
    # EDT (UTC-4): NY opens at 12:00 UTC in summer (08:00 EDT)
    label_summer = get_current_session(utc(2026, 7, 16, 12, 30), config)
    assert label_summer in (SessionLabel.NEW_YORK, SessionLabel.LONDON_NY_OVERLAP)

    # EST (UTC-5): 12:30 UTC in winter = 07:30 EST → NY NOT yet open (opens 13:00 UTC)
    label_winter = get_current_session(utc(2026, 1, 15, 12, 30), config)
    assert label_winter not in (SessionLabel.NEW_YORK, SessionLabel.LONDON_NY_OVERLAP)
