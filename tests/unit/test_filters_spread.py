"""Unit tests for spread_filter — 8 tests covering threshold, boundary, invalid spread."""
import pytest

from src.filters.models import FilterResult
from src.filters.spread_filter import check_spread


@pytest.fixture
def config():
    return {"filters": {"spread": {"max_spread_usd": 0.50}}}


def config_with_threshold(threshold: float) -> dict:
    return {"filters": {"spread": {"max_spread_usd": threshold}}}


# --- Allowed ---

def test_spread_below_threshold_allowed(config):
    decision = check_spread(0.30, config)
    assert decision.result == FilterResult.ALLOWED


def test_spread_at_exact_threshold_allowed(config):
    # spec says "exceeds" — equal to threshold is NOT blocked
    decision = check_spread(0.50, config)
    assert decision.result == FilterResult.ALLOWED


def test_spread_config_threshold_applied():
    # custom threshold $0.80 — $0.70 should pass
    decision = check_spread(0.70, config_with_threshold(0.80))
    assert decision.result == FilterResult.ALLOWED


# --- Blocked: spread too wide ---

def test_spread_above_threshold_blocked(config):
    decision = check_spread(1.20, config)
    assert decision.result == FilterResult.BLOCKED
    assert decision.reason == "SPREAD_TOO_WIDE"


def test_spread_one_cent_over_blocked(config):
    # $0.51 just over $0.50 threshold → BLOCKED
    decision = check_spread(0.51, config)
    assert decision.result == FilterResult.BLOCKED
    assert decision.reason == "SPREAD_TOO_WIDE"


# --- Blocked: invalid spread ---

def test_spread_zero_invalid_blocked(config):
    decision = check_spread(0.0, config)
    assert decision.result == FilterResult.BLOCKED
    assert decision.reason == "INVALID_SPREAD"


def test_spread_negative_invalid_blocked(config):
    decision = check_spread(-0.10, config)
    assert decision.result == FilterResult.BLOCKED
    assert decision.reason == "INVALID_SPREAD"


# --- Metric value logged correctly ---

def test_spread_metric_value_logged(config):
    decision = check_spread(0.28, config)
    assert decision.metric_value == 0.28
