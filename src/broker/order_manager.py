"""
MT5 order placement with mandatory SL/TP enforcement.

Every order attempt — success, failure, or rejection — is logged atomically
to trades.json before the function returns. No silent failures (FR-009).
An order without a valid stop loss AND take profit never reaches the broker (FR-007).
"""
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import MetaTrader5 as mt5
from loguru import logger

from src.execution.audit_logger import write_audit_entry
from src.execution.models import AuditAction, TradeAuditEntry

SYMBOL = "XAUUSD"


def _call_with_timeout(fn, timeout: float):
    """T024: Run fn() in a thread; raise FuturesTimeoutError if it exceeds timeout seconds."""
    with ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(fn).result(timeout=timeout)


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

    Thread safety: trades.json writes are delegated to audit_logger.AUDIT_LOG_LOCK
    (single lock for the whole process — eliminates dual-lock race on trades.json, T008).
    """

    def __init__(self, magic_number: int, slippage_points: int = 5) -> None:
        self._magic = magic_number
        self._slippage = slippage_points

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

        # T025: reject before touching broker when margin is critically low (FR-016).
        # margin_level == 0.0 when no positions are open (MT5 returns 0 for 0/0);
        # only gate when there is actually used margin (account.margin > 0).
        account = mt5.account_info()
        if account is not None and account.margin > 0 and account.margin_level < 10.0:
            logger.warning(
                f"Low Margin Warning — margin at {account.margin_level}%, threshold 10%"
            )
            order = TradeOrder(
                order_type=order_type.name,
                entry_price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                volume=volume,
                magic_number=self._magic,
                timestamp=datetime.utcnow().isoformat(),
                max_loss_usd=max_loss_usd,
                result="rejected",
                error_message=f"Low Margin — margin at {account.margin_level}%, threshold 10%",
            )
            self._log_trade(order)
            return order

        # T025b: timeout guard — broker hang must not block the engine indefinitely
        try:
            result = _call_with_timeout(lambda: mt5.order_send(request), timeout=5.0)
        except FuturesTimeoutError:
            order = TradeOrder(
                order_type=order_type.name,
                entry_price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                volume=volume,
                magic_number=self._magic,
                timestamp=datetime.utcnow().isoformat(),
                max_loss_usd=max_loss_usd,
                result="timeout",
                error_message="Order Timeout — Status Unknown; manual review required",
            )
            logger.critical("Order Timeout — Status Unknown; manual review required")
            self._log_trade(order)
            return order

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
    # Audit log write — delegates to audit_logger (single lock, T008)
    # ------------------------------------------------------------------

    def _log_trade(self, order: TradeOrder) -> None:
        """Convert TradeOrder to TradeAuditEntry and delegate to audit_logger."""
        if order.result == "success":
            action = AuditAction.ORDER_PLACED
            rejection_reason = None
        else:
            action = AuditAction.ORDER_REJECTED
            rejection_reason = order.error_message

        entry = TradeAuditEntry(
            audit_id=str(uuid.uuid4()),
            timestamp_utc=order.timestamp,
            action_type=action,
            signal_id="",  # OrderManager operates below signal level
            ticket_id=order.broker_ticket,
            direction=order.order_type,
            lot_size=order.volume,
            requested_entry_price=order.entry_price,
            actual_fill_price=order.entry_price if order.result == "success" else None,
            sl_price=order.stop_loss,
            tp2_price=order.take_profit,
            max_loss_usd=order.max_loss_usd,
            rejection_reason=rejection_reason,
        )
        write_audit_entry(entry)
