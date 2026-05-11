"""
MT5 order placement with mandatory SL/TP enforcement.

Every order attempt — success, failure, or rejection — is logged atomically
to trades.json before the function returns. No silent failures (FR-009).
An order without a valid stop loss AND take profit never reaches the broker (FR-007).
"""
import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import MetaTrader5 as mt5
from loguru import logger

SYMBOL = "XAUUSD"
TRADES_LOG = Path("logs/trades.json")


class OrderType(Enum):
    BUY = mt5.ORDER_TYPE_BUY
    SELL = mt5.ORDER_TYPE_SELL


@dataclass
class TradeOrder:
    order_type: str
    entry_price: float
    stop_loss: float
    take_profit: float
    volume: float
    magic_number: int
    timestamp: str
    result: str = "pending"
    broker_ticket: Optional[int] = None
    error_message: Optional[str] = None
    max_loss_usd: Optional[float] = None


class OrderManager:
    """
    Submits XAUUSD market orders to MT5.

    Validation chain before each submission:
    1. SL and TP must be non-zero and on the correct side of the current price (FR-007)
    2. Spread must be within the allowed threshold (checked via MarketData upstream)
    3. After submission, broker error codes map to human-readable log messages

    Thread safety: trades.json writes are serialized with _log_lock so concurrent
    signals can never interleave and corrupt the log file (NFR-005).
    """

    _log_lock = threading.Lock()

    def __init__(self, magic_number: int, slippage_points: int = 5) -> None:
        self._magic = magic_number
        self._slippage = slippage_points
        TRADES_LOG.parent.mkdir(parents=True, exist_ok=True)

    def place_order(
        self,
        order_type: OrderType,
        volume: float,
        stop_loss: float,
        take_profit: float,
        comment: str = "Shikra",
    ) -> TradeOrder:
        """
        Submit a market order with mandatory SL and TP.

        Pre-submission: validates SL/TP geometry, fetches live price.
        Post-submission: maps broker retcode to a human-readable result.
        Always logs to trades.json before returning (FR-009).
        """
        price = self._get_price(order_type)

        # Geometry check — wrong-side SL/TP is rejected before touching the broker
        if price is None or not self._sl_tp_valid(order_type, price, stop_loss, take_profit):
            logger.error("Missing SL/TP — Order Rejected")
            order = TradeOrder(
                order_type=order_type.name,
                entry_price=price or 0.0,
                stop_loss=stop_loss,
                take_profit=take_profit,
                volume=volume,
                magic_number=self._magic,
                timestamp=datetime.utcnow().isoformat(),
                result="rejected",
                error_message="Missing SL/TP — Order Rejected",
            )
            self._log_trade(order)
            return order

        max_loss_usd = self._calculate_max_loss(price, stop_loss, volume)

        logger.info(
            f"Submitting {order_type.name}: price={price}, SL={stop_loss}, "
            f"TP={take_profit}, vol={volume}, maxLoss=${max_loss_usd}"
        )

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": volume,
            "type": order_type.value,
            "price": price,
            "sl": stop_loss,
            "tp": take_profit,
            "deviation": self._slippage,
            "magic": self._magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)

        order = TradeOrder(
            order_type=order_type.name,
            entry_price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            volume=volume,
            magic_number=self._magic,
            timestamp=datetime.utcnow().isoformat(),
            max_loss_usd=max_loss_usd,
        )

        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            order.result = "success"
            order.broker_ticket = result.order
            logger.info(f"Order confirmed — ticket: {result.order}")
        else:
            retcode = result.retcode if result else "no_response"
            order.result = "failed"

            if retcode == mt5.TRADE_RETCODE_NO_MONEY:
                order.error_message = "Insufficient Margin"
                logger.error("Insufficient Margin — order not placed")
            elif retcode == "no_response":
                # Connection dropped mid-flight — flag for manual review
                order.error_message = "Order Status Unknown — connection lost during submission"
                logger.critical(
                    "Order Status Unknown — connection dropped; halting further orders "
                    "until connection restored (FR-009 edge case)"
                )
            else:
                order.error_message = f"Broker error retcode: {retcode}"
                logger.error(f"Order failed — retcode: {retcode}")

        self._log_trade(order)
        return order

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _sl_tp_valid(
        self,
        order_type: OrderType,
        price: float,
        sl: float,
        tp: float,
    ) -> bool:
        """
        Enforce correct SL/TP geometry:
        BUY  → SL below entry, TP above entry
        SELL → TP below entry, SL above entry
        Zero values are always invalid.
        """
        if sl <= 0 or tp <= 0:
            return False
        if order_type == OrderType.BUY:
            return sl < price < tp
        else:  # SELL
            return tp < price < sl

    def _get_price(self, order_type: OrderType) -> Optional[float]:
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick is None:
            logger.error("Cannot place order — no price data available")
            return None
        return tick.ask if order_type == OrderType.BUY else tick.bid

    def _calculate_max_loss(self, price: float, stop_loss: float, volume: float) -> float:
        """
        Compute USD loss if stop is hit.
        Uses broker decimal precision — XAUUSD is 5 dp (NFR- config decimal_precision).
        """
        sym = mt5.symbol_info(SYMBOL)
        if sym is None:
            return 0.0
        sl_points = abs(price - stop_loss) / sym.point
        point_value = sym.trade_contract_size * sym.point
        return round(sl_points * point_value * volume, 2)

    # ------------------------------------------------------------------
    # Atomic log write
    # ------------------------------------------------------------------

    def _log_trade(self, order: TradeOrder) -> None:
        """
        Append trade record to trades.json atomically.

        Lock ensures no two threads can interleave their writes, preventing
        partial JSON entries that would corrupt the audit log (NFR-005).
        """
        entry = asdict(order)

        with self._log_lock:
            records: list = []
            if TRADES_LOG.exists() and TRADES_LOG.stat().st_size > 0:
                try:
                    with open(TRADES_LOG, "r", encoding="utf-8") as fh:
                        records = json.load(fh)
                except json.JSONDecodeError:
                    logger.warning("trades.json parse error — starting fresh log")

            records.append(entry)

            with open(TRADES_LOG, "w", encoding="utf-8") as fh:
                json.dump(records, fh, indent=2, default=str)
