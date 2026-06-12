"""Unit tests for src/backtest/data_loader.py — spec009 T016."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.analysis.models import Timeframe
from src.backtest.data_loader import load_ohlcv_csv

# ── CSV templates ─────────────────────────────────────────────────────────────

_VALID_CSV = """\
date,time,open,high,low,close,tick_volume
2024.01.01,01:00,2000.10,2010.50,1995.30,2005.75,1200
2024.01.01,02:00,2005.75,2015.00,2000.00,2012.30,980
2024.01.01,03:00,2012.30,2020.00,2008.00,2018.90,1100
"""

_EXTRA_COLUMNS_CSV = """\
date,time,open,high,low,close,volume,spread,source
2024.01.01,01:00,2000.10,2010.50,1995.30,2005.75,1200,0.30,mt5
"""

_MISSING_COLUMN_CSV = """\
date,time,open,high,close,tick_volume
2024.01.01,01:00,2000.10,2010.50,2005.75,1200
"""

_MIXED_CASE_CSV = """\
DATE,TIME,Open,HIGH,LOW,Close,Volume
2024.01.01,01:00,2000.10,2010.50,1995.30,2005.75,1200
"""


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content)
    return p


# ── Test 1: valid CSV ──────────────────────────────────────────────────────────

class TestValidCsv:
    def test_loads_and_returns_sorted_bars(self, tmp_path):
        """Valid CSV must return OHLCVBars sorted oldest-first with correct field values."""
        _write(tmp_path, "XAUUSD_H1.csv", _VALID_CSV)
        bars = load_ohlcv_csv(tmp_path, Timeframe.H1)

        assert len(bars) == 3
        assert bars[0].timestamp.hour == 1
        assert bars[2].timestamp.hour == 3
        assert bars[0].open == pytest.approx(2000.10)
        assert bars[0].high == pytest.approx(2010.50)
        assert bars[0].low  == pytest.approx(1995.30)
        assert bars[0].close == pytest.approx(2005.75)
        assert bars[0].volume == pytest.approx(1200.0)


# ── Test 2: missing file ──────────────────────────────────────────────────────

class TestMissingFile:
    def test_raises_file_not_found(self, tmp_path):
        """Non-existent CSV must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="XAUUSD_H1.csv"):
            load_ohlcv_csv(tmp_path, Timeframe.H1)


# ── Test 3: missing required column ──────────────────────────────────────────

class TestMissingColumn:
    def test_raises_value_error_on_missing_low(self, tmp_path):
        """CSV missing the 'low' column must raise ValueError naming the absent column."""
        _write(tmp_path, "XAUUSD_H1.csv", _MISSING_COLUMN_CSV)
        with pytest.raises(ValueError, match="low"):
            load_ohlcv_csv(tmp_path, Timeframe.H1)


# ── Test 4: field mapping (date + time → timestamp) ──────────────────────────

class TestFieldMapping:
    def test_datetime_parsed_from_separate_columns(self, tmp_path):
        """date and time columns must be combined into a UTC-aware timestamp."""
        from datetime import timezone
        _write(tmp_path, "XAUUSD_H1.csv", _VALID_CSV)
        bars = load_ohlcv_csv(tmp_path, Timeframe.H1)

        assert bars[0].timestamp.year    == 2024
        assert bars[0].timestamp.month   == 1
        assert bars[0].timestamp.day     == 1
        assert bars[0].timestamp.hour    == 1
        assert bars[0].timestamp.minute  == 0
        assert bars[0].timestamp.tzinfo  == timezone.utc


# ── Test 5: extra columns ignored ────────────────────────────────────────────

class TestExtraColumnsIgnored:
    def test_extra_columns_do_not_raise(self, tmp_path):
        """CSV with extra columns ('spread', 'source') must load without errors."""
        _write(tmp_path, "XAUUSD_H1.csv", _EXTRA_COLUMNS_CSV)
        bars = load_ohlcv_csv(tmp_path, Timeframe.H1)
        assert len(bars) == 1
        assert bars[0].open == pytest.approx(2000.10)

    def test_mixed_case_columns_accepted(self, tmp_path):
        """Column names should be matched case-insensitively."""
        _write(tmp_path, "XAUUSD_H1.csv", _MIXED_CASE_CSV)
        bars = load_ohlcv_csv(tmp_path, Timeframe.H1)
        assert len(bars) == 1
