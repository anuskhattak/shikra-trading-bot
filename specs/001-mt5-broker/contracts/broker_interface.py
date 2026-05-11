"""
Broker interface contract for the Shikra trading system.

Any broker implementation (MT5, paper trading, backtest mock) MUST satisfy
this protocol so the signal engine and risk manager are broker-agnostic.
"""
from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd

from src.broker.market_data import MarketQuote, Timeframe
from src.broker.order_manager import OrderType, TradeOrder


class BrokerInterface(ABC):
    """Abstract contract every broker adapter must fulfil."""

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def connect(self) -> bool:
        """Establish and authenticate broker connection. Returns True on success."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Cleanly release the broker connection."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """True when broker connection is active and authenticated."""
        ...

    @property
    @abstractmethod
    def uptime_percent(self) -> float:
        """Connection uptime % since session start. Must be ≥ 99% per NFR-002."""
        ...

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    @abstractmethod
    def get_quote(self) -> Optional[MarketQuote]:
        """
        Current XAUUSD bid/ask/spread.
        Returns None when market is closed OR spread exceeds threshold.
        """
        ...

    @abstractmethod
    def get_ohlcv(self, timeframe: Timeframe, count: int = 200) -> Optional[pd.DataFrame]:
        """
        Historical OHLCV bars. Returns None when fewer than 200 bars available.
        DataFrame columns: open, high, low, close, volume. Index: datetime (UTC).
        """
        ...

    @abstractmethod
    def is_market_open(self) -> bool:
        """False on weekends, holidays, or broker outages."""
        ...

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    @abstractmethod
    def place_order(
        self,
        order_type: OrderType,
        volume: float,
        stop_loss: float,
        take_profit: float,
        comment: str = "Shikra",
    ) -> TradeOrder:
        """
        Submit a market order. SL and TP are mandatory.
        Returns TradeOrder with result field: success / failed / rejected.
        Always logs to trades.json before returning — no silent failures.
        """
        ...
