"""Data models for the session & pre-trade filter pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Union


class FilterResult(Enum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"


class SessionLabel(Enum):
    ASIAN             = "ASIAN"
    LONDON            = "LONDON"
    NEW_YORK          = "NEW_YORK"
    LONDON_NY_OVERLAP = "LONDON_NY_OVERLAP"
    CLOSED            = "CLOSED"


class VolatilityRegime(Enum):
    LOW     = "LOW"
    NORMAL  = "NORMAL"
    EXTREME = "EXTREME"


class NewsImpact(Enum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"


@dataclass
class SessionWindow:
    """Named session window parsed from config."""
    name:        str
    local_open:  str   # "08:00" — local market time
    local_close: str   # "17:00" — local market time
    timezone:    str   # IANA zone e.g. "Europe/London"
    enabled:     bool


@dataclass
class FilterDecision:
    """Result of one filter evaluation."""
    filter_name:  str
    result:       FilterResult
    reason:       str
    metric_value: Union[float, str]
    timestamp:    datetime


@dataclass
class TradeGateResult:
    """Aggregated result for one signal evaluation."""
    signal_id:    str
    final_result: FilterResult
    decisions:    list[FilterDecision]
    evaluated_at: datetime


@dataclass
class NewsEvent:
    """One scheduled economic event."""
    name:          str
    impact:        NewsImpact
    scheduled_utc: datetime
    currencies:    list[str]


@dataclass
class VolatilityReading:
    """ATR regime snapshot returned by classify_regime()."""
    regime:        VolatilityRegime
    current_atr:   float
    reference_atr: float
    ratio:         float          # current_atr / reference_atr
    timestamp:     datetime
