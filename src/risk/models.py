"""Data model for the Risk Management Module (spec003).

All types are broker-agnostic — no MT5 import (NFR-001).
RiskState uses functional update pattern: functions always return a new instance (NFR-003).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class RecoveryReason(Enum):
    """Why recovery mode was entered."""

    CONSECUTIVE_LOSSES = "consecutive_losses"


class BlockReason(Enum):
    """Reason a trade evaluation was blocked."""

    DRAWDOWN_LIMIT = "daily_drawdown_limit"
    DAILY_TRADE_LIMIT = "daily_trade_limit"
    SESSION_TRADE_LIMIT = "session_trade_limit"
    COOLDOWN_ACTIVE = "cooldown_active_after_sl"
    NOT_BLOCKED = "not_blocked"


@dataclass
class RiskCalculation:
    """Output of evaluate_trade_risk(). Holds all values needed to place an order.

    Invariants:
        LONG:  sl_price < entry_price < tp1_price < tp2_price
        SHORT: tp2_price < tp1_price < entry_price < sl_price
        lot_size in [min_lot, max_lot_size]
        risk_amount_usd <= balance * 0.05
    When lot_size == 0.0 the trade is blocked; caller must not submit an order.
    """

    lot_size: float
    sl_price: float
    tp1_price: float
    tp2_price: float
    sl_distance: float       # SL move in price units (e.g. 30.0 = $30); used for audit
    risk_amount_usd: float
    in_recovery: bool
    reason: str


@dataclass
class RiskState:
    """Mutable session state owned by the caller (main loop), never a singleton.

    Initialise with day_start_equity = current equity at bot startup.
    Mid-day restart resets that day's drawdown history — documented limitation (FR-015a).
    """

    day_start_equity: float
    trades_today: int = 0
    session_trades: dict[str, int] = field(default_factory=dict)
    last_sl_time: datetime | None = None
    consecutive_losses: int = 0
    in_recovery_mode: bool = False
    recovery_profit_pips: float = 0.0


@dataclass
class TradeAllowedResult:
    """Result of check_drawdown() and is_trade_limit_allowed()."""

    allowed: bool
    reason: str  # "not_blocked" when allowed=True; human-readable block description otherwise
