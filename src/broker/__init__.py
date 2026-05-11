"""
Shikra broker module — MT5 connection, market data, and order management.

Public API:
    BrokerConnection  — connect / disconnect / health monitor
    MarketData        — live quotes and historical OHLCV
    OrderManager      — order placement with mandatory SL/TP

Usage:
    from src.broker import BrokerConnection, MarketData, OrderManager
"""
from .connection import BrokerConnection, ConnectionEvent, ConnectionStatus
from .market_data import MarketData, MarketQuote, Timeframe
from .order_manager import OrderManager, OrderType, TradeOrder

__all__ = [
    "BrokerConnection",
    "ConnectionEvent",
    "ConnectionStatus",
    "MarketData",
    "MarketQuote",
    "Timeframe",
    "OrderManager",
    "OrderType",
    "TradeOrder",
]
