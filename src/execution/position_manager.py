"""Position lifecycle management — trailing stop, partial close, reconciliation."""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime
from typing import Optional

import MetaTrader5 as mt5
from loguru import logger

from src.execution.audit_logger import write_audit_entry
from src.execution.models import AuditAction, Direction, PositionState, TradeAuditEntry

SYMBOL = "XAUUSD"


# ---------------------------------------------------------------------------
# T016 — evaluate_trailing_stop (pure function — no MT5 calls)
# ---------------------------------------------------------------------------

def evaluate_trailing_stop(
    position: PositionState,
    current_price: float,
    config: dict,
) -> tuple[PositionState, Optional[TradeAuditEntry]]:
    """Return updated trailing stop state without calling MT5 (FR-008, FR-009, FR-010).

    LONG:  activates when price >= entry + activation_distance.
           new_sl = price - trailing_distance; applied only when new_sl > current_sl.
    SHORT: symmetric — activates when price <= entry - activation_distance.
           new_sl = price + trailing_distance; applied only when new_sl < current_sl.

    Caller must apply the new SL via _apply_sl_modification() if entry is not None.
    """
    activation_distance = config.get("activation_distance", 30.0)
    trailing_distance = config.get("trailing_distance", 20.0)

    if position.direction == Direction.LONG:
        if current_price < position.entry_price + activation_distance:
            return position, None
        new_sl = current_price - trailing_distance
        if new_sl <= position.current_sl:  # unidirectional — never move SL back down
            return position, None

    elif position.direction == Direction.SHORT:
        if current_price > position.entry_price - activation_distance:
            return position, None
        new_sl = current_price + trailing_distance
        if new_sl >= position.current_sl:  # unidirectional — never move SL back up
            return position, None

    else:
        return position, None

    updated = replace(position, current_sl=new_sl, trailing_activated=True)
    entry = TradeAuditEntry(
        audit_id=str(uuid.uuid4()),
        timestamp_utc=datetime.utcnow().isoformat(),
        action_type=AuditAction.TRAILING_STOP_UPDATED,
        signal_id=position.signal_id,
        ticket_id=position.ticket_id,
        direction=position.direction.value,
        new_sl_price=new_sl,
    )
    return updated, entry


# ---------------------------------------------------------------------------
# T017 — _apply_sl_modification (MT5 SLTP request, retry once on failure)
# ---------------------------------------------------------------------------

def _apply_sl_modification(
    ticket_id: int,
    new_sl: float,
    tp_price: float,
    signal_id: str = "",
) -> tuple[bool, str]:
    """Send TRADE_ACTION_SLTP via mt5.order_send(); retry once on failure (US2 S4).

    On second failure: writes SL_MODIFICATION_FAILED audit entry and returns (False, reason).
    Returns (True, "") on any successful attempt.
    """
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": SYMBOL,
        "position": ticket_id,
        "sl": new_sl,
        "tp": tp_price,
    }

    reason = "unknown"
    for attempt in range(2):
        result = mt5.order_send(request)
        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            return True, ""
        reason = f"retcode {result.retcode}" if result is not None else "no response"
        logger.warning(
            f"SL modification attempt {attempt + 1}/2 failed — ticket {ticket_id}, {reason}"
        )

    logger.error(
        f"SL modification failed after 2 attempts — ticket {ticket_id}, new_sl {new_sl}"
    )
    _write_sl_failed_entry(ticket_id, new_sl, signal_id, reason)
    return False, reason


def _write_sl_failed_entry(
    ticket_id: int,
    new_sl: float,
    signal_id: str,
    reason: str,
) -> None:
    write_audit_entry(TradeAuditEntry(
        audit_id=str(uuid.uuid4()),
        timestamp_utc=datetime.utcnow().isoformat(),
        action_type=AuditAction.SL_MODIFICATION_FAILED,
        signal_id=signal_id,
        ticket_id=ticket_id,
        new_sl_price=new_sl,
        rejection_reason=reason,
    ))


# ---------------------------------------------------------------------------
# T019 — apply_partial_close (US3: TP1 hit → close 50%, move SL to breakeven)
# ---------------------------------------------------------------------------

def apply_partial_close(
    position: PositionState,
    config: dict,
) -> tuple[PositionState, list[TradeAuditEntry]]:
    """Close tp1_close_ratio of position and move SL to entry price (FR-011, FR-012).

    On success: reduces lot_size, marks partial_close_done=True, calls
    _apply_sl_modification() with new_sl=entry_price (BREAKEVEN_SET).
    Returns (updated_state, [PARTIAL_CLOSE, BREAKEVEN_SET]) on success.
    On broker failure: writes PARTIAL_CLOSE failure entry via audit_logger and
    returns (unchanged_state, []).
    """
    close_ratio = config.get("tp1_close_ratio", 0.5)
    close_lots = round(position.lot_size * close_ratio, 2)

    if close_lots > position.lot_size:
        # Floating-point or misconfigured ratio guard — never send more than we hold
        logger.warning(
            f"close_lots {close_lots} > lot_size {position.lot_size} "
            f"for ticket {position.ticket_id} — clamping to position size"
        )
        close_lots = position.lot_size

    if close_lots <= 0.0:
        logger.warning(
            f"Computed close_lots=0 for ticket {position.ticket_id} — skipping partial close"
        )
        return position, []

    order_type = mt5.ORDER_TYPE_SELL if position.direction == Direction.LONG else mt5.ORDER_TYPE_BUY

    tick = mt5.symbol_info_tick(SYMBOL)
    price = tick.bid if (tick is not None and position.direction == Direction.LONG) else (
        tick.ask if tick is not None else 0.0
    )

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": close_lots,
        "type": order_type,
        "position": position.ticket_id,
        "price": price,
        "deviation": config.get("slippage_points", 5),
        "magic": config.get("magic_number", 0),
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
        fill_price = getattr(result, "price", price)
        new_lot_size = round(position.lot_size - close_lots, 2)
        updated = replace(position, lot_size=new_lot_size, partial_close_done=True)

        entries: list[TradeAuditEntry] = [
            TradeAuditEntry(
                audit_id=str(uuid.uuid4()),
                timestamp_utc=datetime.utcnow().isoformat(),
                action_type=AuditAction.PARTIAL_CLOSE,
                signal_id=position.signal_id,
                ticket_id=position.ticket_id,
                direction=position.direction.value,
                lot_size=close_lots,
                exit_price=fill_price,
                exit_reason="TP1 hit — partial close",
            )
        ]

        # Move SL to breakeven regardless of _apply_sl_modification failure
        ok, _ = _apply_sl_modification(
            position.ticket_id, position.entry_price, position.tp2_price, position.signal_id
        )
        if ok:
            updated = replace(updated, current_sl=position.entry_price)
            entries.append(TradeAuditEntry(
                audit_id=str(uuid.uuid4()),
                timestamp_utc=datetime.utcnow().isoformat(),
                action_type=AuditAction.BREAKEVEN_SET,
                signal_id=position.signal_id,
                ticket_id=position.ticket_id,
                new_sl_price=position.entry_price,
            ))

        return updated, entries

    reason = f"retcode {result.retcode}" if result is not None else "no response"
    logger.error(f"Partial close failed for ticket {position.ticket_id}: {reason}")
    write_audit_entry(TradeAuditEntry(
        audit_id=str(uuid.uuid4()),
        timestamp_utc=datetime.utcnow().isoformat(),
        action_type=AuditAction.PARTIAL_CLOSE,
        signal_id=position.signal_id,
        ticket_id=position.ticket_id,
        rejection_reason=reason,
        exit_reason="partial close order rejected by broker",
    ))
    return position, []


# ---------------------------------------------------------------------------
# T020 helpers — _full_close + reconcile_positions
# ---------------------------------------------------------------------------

def _full_close(
    position: PositionState,
    current_price: float,
    config: dict,
) -> Optional[TradeAuditEntry]:
    """Send a counter-direction TRADE_ACTION_DEAL to fully close position at TP2.

    Returns a FULL_CLOSE TradeAuditEntry on broker success, None on failure.
    Failure is logged to stderr; caller must decide how to handle a missing entry.
    """
    order_type = mt5.ORDER_TYPE_SELL if position.direction == Direction.LONG else mt5.ORDER_TYPE_BUY

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": position.lot_size,
        "type": order_type,
        "position": position.ticket_id,
        "price": current_price,
        "deviation": config.get("slippage_points", 5),
        "magic": config.get("magic_number", 0),
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
        fill_price = getattr(result, "price", current_price)
        return TradeAuditEntry(
            audit_id=str(uuid.uuid4()),
            timestamp_utc=datetime.utcnow().isoformat(),
            action_type=AuditAction.FULL_CLOSE,
            signal_id=position.signal_id,
            ticket_id=position.ticket_id,
            direction=position.direction.value,
            exit_price=fill_price,
            exit_reason="TP2 hit — full close",
        )

    reason = f"retcode {result.retcode}" if result is not None else "no response"
    logger.error(f"Full close failed for ticket {position.ticket_id}: {reason}")
    return None


def reconcile_positions(
    positions: dict[int, PositionState],
) -> tuple[dict[int, PositionState], list[TradeAuditEntry]]:
    """Detect positions closed externally (SL hit, manual close) and prune from dict (FR-014).

    Compares tracked tickets against mt5.positions_get(). Any ticket absent from the
    broker response is treated as externally closed — POSITION_EXTERNALLY_CLOSED entry
    written and ticket removed from the returned dict.
    Returns (pruned_dict, audit_entries).
    """
    broker_positions = mt5.positions_get(symbol=SYMBOL)
    if broker_positions is None:
        logger.warning("reconcile_positions: mt5.positions_get() returned None — skipping")
        return positions, []

    broker_tickets = {p.ticket for p in broker_positions}
    pruned = dict(positions)
    entries: list[TradeAuditEntry] = []

    for ticket_id, pos in list(positions.items()):
        if ticket_id not in broker_tickets:
            entries.append(TradeAuditEntry(
                audit_id=str(uuid.uuid4()),
                timestamp_utc=datetime.utcnow().isoformat(),
                action_type=AuditAction.POSITION_EXTERNALLY_CLOSED,
                signal_id=pos.signal_id,
                ticket_id=ticket_id,
                direction=pos.direction.value,
                exit_reason="position absent from broker — SL hit or manual close",
            ))
            del pruned[ticket_id]

    return pruned, entries


# ---------------------------------------------------------------------------
# T021 — manage_positions (bar-level entry point)
# ---------------------------------------------------------------------------

def manage_positions(
    positions: dict[int, PositionState],
    current_price: float,
    config: dict,
) -> tuple[dict[int, PositionState], list[TradeAuditEntry]]:
    """Bar-level position lifecycle: reconcile → TP2 close → TP1 partial → trail (D-006).

    Fixed per-position step order:
      1. reconcile_positions() — detect externally closed positions
      2. TP2 hit → full close (position removed; trailing NOT evaluated on same bar)
      3. TP1 hit and not partial_close_done → apply_partial_close()
      4. evaluate_trailing_stop() → if SL moved: _apply_sl_modification()
    Returns (updated_positions_dict, all_audit_entries). Never raises.
    """
    all_entries: list[TradeAuditEntry] = []

    positions, reconcile_entries = reconcile_positions(positions)
    all_entries.extend(reconcile_entries)

    updated_positions = dict(positions)

    for ticket_id, pos in list(positions.items()):
        # Step 2: TP2 hit → full close; skip trailing on same bar
        tp2_hit = (
            (pos.direction == Direction.LONG and current_price >= pos.tp2_price)
            or (pos.direction == Direction.SHORT and current_price <= pos.tp2_price)
        )
        if tp2_hit:
            close_entry = _full_close(pos, current_price, config)
            if close_entry is not None:
                all_entries.append(close_entry)
            del updated_positions[ticket_id]
            continue

        # Step 3: TP1 hit and partial not yet done
        tp1_hit = (
            (pos.direction == Direction.LONG and current_price >= pos.tp1_price)
            or (pos.direction == Direction.SHORT and current_price <= pos.tp1_price)
        )
        if tp1_hit and not pos.partial_close_done:
            pos, partial_entries = apply_partial_close(pos, config)
            updated_positions[ticket_id] = pos
            all_entries.extend(partial_entries)

        # Step 4: Trailing stop evaluation
        updated_pos, trail_entry = evaluate_trailing_stop(pos, current_price, config)
        if trail_entry is not None:
            ok, _ = _apply_sl_modification(
                pos.ticket_id, updated_pos.current_sl, pos.tp2_price, pos.signal_id
            )
            if ok:
                updated_positions[ticket_id] = updated_pos
                all_entries.append(trail_entry)

    return updated_positions, all_entries
