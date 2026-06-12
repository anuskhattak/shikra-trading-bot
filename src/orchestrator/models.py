"""Shared data containers for the Strategy Orchestrator and Backtest Engine (spec009)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.analysis.h4_bias import H4BiasResult

from src.analysis.models import ATRReading, OHLCVBar, Timeframe
from src.engine.models import EntrySignal
from src.filters.models import NewsEvent, TradeGateResult
from src.risk.models import RiskCalculation


@dataclass
class PipelineContext:
    """State container for one bar's full evaluation — shared by live and backtest modes.

    Input fields are populated by the caller before run_pipeline().
    Output fields (atr_readings, entry_signal, filter_result, risk_calc) are
    populated stage-by-stage inside run_pipeline().
    """
    signal_id:     str
    timeframe:     Timeframe
    bars:          dict[Timeframe, list[OHLCVBar]]
    now_utc:       datetime
    spread_usd:    float
    news_events:   list[NewsEvent]
    mode:          str              # "live" | "backtest"
    balance:       float = 10000.0
    current_equity: float = 10000.0

    # Output fields — populated by run_pipeline() stages
    atr_readings:    dict[Timeframe, ATRReading]  = field(default_factory=dict)
    entry_signal:    Optional[EntrySignal]         = None
    filter_result:   Optional[TradeGateResult]     = None
    risk_calc:       Optional[RiskCalculation]     = None
    h4_bias_result:  Optional[H4BiasResult]        = None


@dataclass
class BarEvent:
    """A newly closed bar on a specific timeframe — triggers ATR refresh and pipeline execution.

    bars_fetched holds the full 150-bar history for all 4 timeframes, pre-fetched by
    poll_for_new_bar() so that run_pipeline() never touches MT5 directly.
    """
    timeframe:   Timeframe
    bar:         OHLCVBar
    detected_at: datetime
    bars_fetched: dict[Timeframe, list[OHLCVBar]]
