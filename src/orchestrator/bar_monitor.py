"""Bar close detection via MT5 polling — only file in src/orchestrator/ that imports MT5.

poll_for_new_bar() is called every 10 seconds by StrategyOrchestrator.run().
It fetches 2 bars to detect a new H1 bar close, then pre-fetches 150 bars for all
4 timeframes so run_pipeline() never touches MT5 directly (FR-003).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import MetaTrader5 as mt5
from loguru import logger

from src.analysis.models import OHLCVBar, Timeframe

SYMBOL = "XAUUSD"


class MT5ConnectionError(Exception):
    """Raised when MT5 returns None for a data request — indicates disconnection."""


def _rates_to_bars(rates) -> list[OHLCVBar]:
    """Convert MT5 rates array to OHLCVBar list, oldest first."""
    return [
        OHLCVBar(
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            volume=float(r["tick_volume"]),
            timestamp=datetime.fromtimestamp(int(r["time"]), tz=timezone.utc),
        )
        for r in rates
    ]


def poll_for_new_bar(
    last_bar_time: Optional[datetime],
    symbol: str = SYMBOL,
    timeframe_mt5: int = Timeframe.H1.value,
    fetch_count: int = 150,
) -> tuple[bool, datetime, dict[Timeframe, list[OHLCVBar]]]:
    """Detect a new H1 bar close by comparing the latest bar timestamp to last_bar_time.

    On first call (last_bar_time=None): always returns True with full bar history.
    On disconnect (MT5 returns None): raises MT5ConnectionError for caller to handle.

    Returns:
        (True, new_bar_time, bars_dict)  — new bar closed; bars_dict ready for pipeline
        (False, last_bar_time, {})       — same bar as before; nothing to process
    """
    # Fetch 2 bars — just enough to read the latest bar's timestamp cheaply
    probe = mt5.copy_rates_from_pos(symbol, timeframe_mt5, 0, 2)
    if probe is None:
        raise MT5ConnectionError(
            f"MT5 returned None for {symbol} probe — connection lost"
        )

    new_time = datetime.fromtimestamp(int(probe[-1]["time"]), tz=timezone.utc)

    if last_bar_time is not None and new_time == last_bar_time:
        return False, last_bar_time, {}

    # New bar (or first call) — pre-fetch full history for all 4 timeframes
    logger.debug(f"New {symbol} bar detected: {new_time}")
    bars_dict: dict[Timeframe, list[OHLCVBar]] = {}
    for tf in Timeframe:
        rates = mt5.copy_rates_from_pos(symbol, tf.value, 0, fetch_count)
        if rates is None:
            raise MT5ConnectionError(
                f"MT5 returned None while fetching {fetch_count} bars for {tf.name}"
            )
        bars_dict[tf] = _rates_to_bars(rates)

    return True, new_time, bars_dict
