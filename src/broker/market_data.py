"""
XAUUSD market data fetcher.

Wraps MT5 tick and bar APIs with strict validation:
- Spread guard rejects ticks above the configured threshold (FR-015)
- Bar count guard rejects partial datasets rather than silently using them (FR-005)
- Market-closed detection prevents stale signal generation
"""
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import MetaTrader5 as mt5
import pandas as pd
from loguru import logger

SYMBOL = "XAUUSD"
MIN_BARS = 200  # Minimum lookback per SMC D1 analysis — SC-003


def _call_with_timeout(fn, timeout: float):
    """T019: Run fn() in a thread; raise FuturesTimeoutError if it exceeds timeout seconds."""
    with ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(fn).result(timeout=timeout)


class Timeframe(Enum):
    """Three-timeframe hierarchy used by the SMC engine."""
    D1 = mt5.TIMEFRAME_D1   # Higher timeframe — major structure, BOS/CHoCH
    H4 = mt5.TIMEFRAME_H4   # Medium timeframe — directional bias, order blocks
    H1 = mt5.TIMEFRAME_H1   # Lower timeframe — entry precision


@dataclass
class MarketQuote:
    symbol: str
    bid: float
    ask: float
    spread_points: int
    timestamp: datetime


class MarketData:
    """
    Fetches and validates live and historical XAUUSD data from MT5.

    Validation rules applied before returning data to the signal engine:
    - Spread > max_spread_points → None (trade skipped, log written)
    - Bar count < MIN_BARS → None (partial data rejected, not silently used)
    - No tick from broker → market-closed state returned
    """

    def __init__(self, max_spread_points: int = 30) -> None:
        self._max_spread = max_spread_points

    def get_quote(self) -> Optional[MarketQuote]:
        """
        Return current bid/ask/spread for XAUUSD.

        Returns None when market is closed OR spread exceeds threshold —
        caller must skip the trade in both cases (FR-004, FR-015).
        """
        # T020: guard against hung broker tick call
        try:
            tick = _call_with_timeout(lambda: mt5.symbol_info_tick(SYMBOL), timeout=2.0)
        except FuturesTimeoutError:
            logger.error("Market Data Timeout — symbol_info_tick did not respond within 2s")
            return None

        if tick is None:
            logger.warning("Market Closed — Weekend or no tick data for XAUUSD")
            return None

        sym = mt5.symbol_info(SYMBOL)
        if sym is None:
            logger.error("Symbol Unavailable — XAUUSD not found on broker")
            return None

        spread = int(round((tick.ask - tick.bid) / sym.point))

        if spread > self._max_spread:
            logger.warning(
                f"High Spread — Trade Skipped: {spread} pts > max {self._max_spread} pts"
            )
            return None

        return MarketQuote(
            symbol=SYMBOL,
            bid=tick.bid,
            ask=tick.ask,
            spread_points=spread,
            timestamp=datetime.utcfromtimestamp(tick.time),
        )

    def get_ohlcv(self, timeframe: Timeframe, count: int = MIN_BARS) -> Optional[pd.DataFrame]:
        """
        Fetch historical OHLCV bars for XAUUSD on the requested timeframe.

        Rejects and logs partial data rather than returning an incomplete DataFrame
        to the signal engine — incomplete data produces false SMC signals (FR-005).
        """
        # T021: guard against hung historical data call
        try:
            rates = _call_with_timeout(
                lambda: mt5.copy_rates_from_pos(SYMBOL, timeframe.value, 0, count),
                timeout=2.0,
            )
        except FuturesTimeoutError:
            logger.error(
                f"Market Data Timeout — copy_rates_from_pos did not respond within 2s "
                f"({timeframe.name})"
            )
            return None

        if rates is None or len(rates) < MIN_BARS:
            actual = len(rates) if rates is not None else 0
            logger.error(
                f"Incomplete Data Warning — {timeframe.name}: got {actual} bars, "
                f"need {MIN_BARS}; discarding dataset"
            )
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.set_index("time")
        df = df[["open", "high", "low", "close", "tick_volume"]].rename(
            columns={"tick_volume": "volume"}
        )

        logger.debug(f"Fetched {len(df)} bars for {SYMBOL} {timeframe.name}")
        return df

    def get_all_timeframes(self) -> dict[str, Optional[pd.DataFrame]]:
        """
        Fetch D1, H4, and H1 bars in a single call.

        All three timeframes are required simultaneously for SMC multi-timeframe
        analysis. Missing any one halts signal generation entirely.
        """
        result: dict[str, Optional[pd.DataFrame]] = {}
        for tf in Timeframe:
            result[tf.name] = self.get_ohlcv(tf)

        missing = [k for k, v in result.items() if v is None]
        if missing:
            logger.error(f"Missing timeframe data: {missing} — signal generation halted")

        return result

    def is_market_open(self) -> bool:
        """
        Return False when XAUUSD has no active tick (weekend / holiday / broker outage).

        Called before every signal cycle so the engine never processes stale data.
        """
        sym = mt5.symbol_info(SYMBOL)
        if sym is None:
            logger.warning("Symbol Unavailable — XAUUSD not found; retrying in 60 s")
            return False

        tick = mt5.symbol_info_tick(SYMBOL)
        if tick is None:
            logger.info("Market Closed — Weekend or holiday detected; entering standby")
            return False

        return True
