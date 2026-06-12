"""Unit tests for src/orchestrator/bar_monitor.py — spec009 T009.

4 tests:
  1. New bar detected — different timestamp returns (True, new_time, bars_dict)
  2. No new bar — same timestamp returns (False, last_time, {})
  3. MT5 returns None on probe → raises MT5ConnectionError
  4. First call with last_bar_time=None → always returns True with bars
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from src.analysis.models import OHLCVBar, Timeframe
from src.orchestrator.bar_monitor import MT5ConnectionError, poll_for_new_bar

_OLD_TS = 1_000_000   # Unix timestamp for "old" bar
_NEW_TS = 1_003_600   # Unix timestamp for "new" bar (+1 hour)

_OLD_DT = datetime.fromtimestamp(_OLD_TS, tz=timezone.utc)
_NEW_DT = datetime.fromtimestamp(_NEW_TS, tz=timezone.utc)


def _fake_rates(ts: int, count: int = 2) -> list[dict]:
    """Return a list of MT5-style rate dicts, last bar having the given timestamp."""
    return [
        {"time": ts - 3600, "open": 2000.0, "high": 2010.0, "low": 1990.0,
         "close": 2005.0, "tick_volume": 100.0},
    ] * (count - 1) + [
        {"time": ts, "open": 2005.0, "high": 2015.0, "low": 1995.0,
         "close": 2008.0, "tick_volume": 120.0},
    ]


# ── Test 1: New bar detected ──────────────────────────────────────────────────

class TestNewBarDetected:
    def test_returns_true_and_bars_dict_when_timestamp_changes(self):
        """Probe returns newer timestamp → (True, new_time, bars_dict) with 4 TF keys."""
        # First call: probe (2 bars), then 4 full-fetch calls (one per Timeframe)
        fake_probe = _fake_rates(_NEW_TS, count=2)
        fake_full  = _fake_rates(_NEW_TS, count=150)

        with patch("src.orchestrator.bar_monitor.mt5") as mock_mt5:
            mock_mt5.copy_rates_from_pos.side_effect = [
                fake_probe,                             # probe call
                fake_full, fake_full, fake_full, fake_full,  # 4 TF fetches
            ]

            result, new_time, bars_dict = poll_for_new_bar(
                last_bar_time=_OLD_DT,
                fetch_count=150,
            )

        assert result is True
        assert new_time == _NEW_DT
        assert set(bars_dict.keys()) == set(Timeframe)
        # Each TF should have 150 OHLCVBar instances
        for tf in Timeframe:
            assert len(bars_dict[tf]) == 150
            assert isinstance(bars_dict[tf][0], OHLCVBar)


# ── Test 2: No new bar ────────────────────────────────────────────────────────

class TestNoNewBar:
    def test_returns_false_and_empty_dict_when_timestamp_unchanged(self):
        """Probe returns same timestamp as last_bar_time → (False, last_time, {})."""
        fake_probe = _fake_rates(_OLD_TS, count=2)

        with patch("src.orchestrator.bar_monitor.mt5") as mock_mt5:
            mock_mt5.copy_rates_from_pos.return_value = fake_probe

            result, returned_time, bars_dict = poll_for_new_bar(
                last_bar_time=_OLD_DT,
            )

        assert result is False
        assert returned_time == _OLD_DT
        assert bars_dict == {}
        # Only one call (probe) — no full-fetch calls issued
        assert mock_mt5.copy_rates_from_pos.call_count == 1


# ── Test 3: MT5 returns None → MT5ConnectionError ────────────────────────────

class TestMT5ReturnsNone:
    def test_raises_mt5_connection_error_when_probe_returns_none(self):
        """MT5 returning None on probe → MT5ConnectionError raised."""
        with patch("src.orchestrator.bar_monitor.mt5") as mock_mt5:
            mock_mt5.copy_rates_from_pos.return_value = None

            with pytest.raises(MT5ConnectionError):
                poll_for_new_bar(last_bar_time=_OLD_DT)


# ── Test 4: First call with last_bar_time=None ────────────────────────────────

class TestFirstCall:
    def test_none_last_bar_time_always_returns_true_with_bars(self):
        """last_bar_time=None (first call) → always returns True regardless of timestamp."""
        fake_probe = _fake_rates(_OLD_TS, count=2)
        fake_full  = _fake_rates(_OLD_TS, count=150)

        with patch("src.orchestrator.bar_monitor.mt5") as mock_mt5:
            mock_mt5.copy_rates_from_pos.side_effect = [
                fake_probe,
                fake_full, fake_full, fake_full, fake_full,
            ]

            result, new_time, bars_dict = poll_for_new_bar(
                last_bar_time=None,
                fetch_count=150,
            )

        assert result is True
        assert new_time == _OLD_DT
        assert len(bars_dict) == len(Timeframe)
