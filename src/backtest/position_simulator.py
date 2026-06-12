"""Bar-level position simulation for the backtest engine — spec009 T017."""
from __future__ import annotations

import copy
from typing import Optional

from src.analysis.models import OHLCVBar
from src.backtest.models import SimulatedPosition, TradeRecord
from src.engine.models import Direction


def simulate_bar(
    position: SimulatedPosition,
    bar: OHLCVBar,
) -> tuple[SimulatedPosition, Optional[TradeRecord]]:
    """Advance one position by one OHLCV bar.

    Conservative rule (D-004): when both SL and TP2 trigger on the same bar, SL wins.
    TP1 partial-close: halves lot_size, moves SL to entry_price (breakeven), keeps position open.
    P&L formula: direction_sign * (exit_price - entry_price) * lot_size * pip_value_per_lot
      LONG  → direction_sign = +1
      SHORT → direction_sign = −1

    Returns (updated_position, trade_record).
    trade_record is None when the position remains open.
    """
    if position.is_closed:
        return position, None

    pos = copy.copy(position)
    is_long = pos.direction == Direction.LONG
    sign = 1.0 if is_long else -1.0

    def _record(exit_price: float, exit_type: str) -> TradeRecord:
        pnl = sign * (exit_price - pos.entry_price) * pos.lot_size * pos.pip_value_per_lot
        return TradeRecord(
            signal_id=pos.signal_id,
            direction=pos.direction,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            exit_type=exit_type,
            pnl_usd=pnl,
            lot_size=pos.lot_size,
            opened_at=pos.opened_at,
            closed_at=bar.timestamp,
            entry_signal_type=pos.entry_signal_type,
            entry_confidence=pos.entry_confidence,
        )

    if not pos.is_tp1_hit:
        sl_hit  = (is_long and bar.low  <= pos.sl_price)  or (not is_long and bar.high >= pos.sl_price)
        tp1_hit = (is_long and bar.high >= pos.tp1_price) or (not is_long and bar.low  <= pos.tp1_price)
        tp2_hit = (is_long and bar.high >= pos.tp2_price) or (not is_long and bar.low  <= pos.tp2_price)

        # Conservative rule: SL always wins when triggered (even if TP2 also triggers)
        if sl_hit:
            pos.is_closed = True
            return pos, _record(pos.sl_price, "SL")

        if tp2_hit:
            pos.is_closed = True
            return pos, _record(pos.tp2_price, "TP2")

        if tp1_hit:
            # Partial close at TP1: halve size, move SL to breakeven, stay open
            pos.lot_size  /= 2.0
            pos.sl_price   = pos.entry_price   # breakeven stop
            pos.is_tp1_hit = True
            return pos, None

    else:
        # After TP1 partial close — SL is now at entry_price (breakeven)
        sl_hit  = (is_long and bar.low  <= pos.sl_price)  or (not is_long and bar.high >= pos.sl_price)
        tp2_hit = (is_long and bar.high >= pos.tp2_price) or (not is_long and bar.low  <= pos.tp2_price)

        # Conservative rule applies here too
        if sl_hit:
            pos.is_closed = True
            return pos, _record(pos.sl_price, "SL")

        if tp2_hit:
            pos.is_closed = True
            return pos, _record(pos.tp2_price, "TP2")

    return pos, None
