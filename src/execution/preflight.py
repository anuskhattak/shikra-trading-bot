"""Pre-flight validation checks — run before every order placement.

Cheapest checks first (D-006): kill-switch → pyramiding → drawdown → margin → min-stop.
Each check returns (allowed: bool, reason: str). run_preflight() short-circuits on first False.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import MetaTrader5 as mt5
from loguru import logger

from src.execution.kill_switch import KILL_SWITCH_PATH, is_kill_switch_active
from src.execution.models import Direction, ExecutionSignal, PositionState
from src.risk.drawdown_guard import check_drawdown

SYMBOL = "XAUUSD"


# ---------------------------------------------------------------------------
# T010 — kill-switch and pyramiding checks (no MT5 calls)
# ---------------------------------------------------------------------------

def check_kill_switch(path: Optional[Path] = None) -> tuple[bool, str]:
    """Return (False, reason) when the kill-switch flag is active (FR-005)."""
    resolved = path if path is not None else KILL_SWITCH_PATH
    if is_kill_switch_active(resolved):
        return False, "kill-switch active"
    return True, ""


def check_existing_position(
    positions: dict[int, PositionState],
    direction: Direction,
) -> tuple[bool, str]:
    """Return (False, reason) when a same-direction position already exists (FR-006)."""
    for pos in positions.values():
        if pos.direction == direction:
            return False, (
                f"pyramiding blocked — {direction.value} position already open "
                f"(ticket {pos.ticket_id})"
            )
    return True, ""


# ---------------------------------------------------------------------------
# T011 — drawdown, margin, and min-stop checks
# ---------------------------------------------------------------------------

def check_daily_drawdown(
    day_start_equity: float,
    current_equity: float,
    max_pct: float,
) -> tuple[bool, str]:
    """Delegate to spec003 check_drawdown(); unpack TradeAllowedResult (FR-004)."""
    result = check_drawdown(day_start_equity, current_equity, max_pct)
    return result.allowed, result.reason


def check_margin_sufficiency(lot_size: float) -> tuple[bool, str]:
    """Call mt5.order_check() to verify account margin is sufficient (FR-003)."""
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        logger.warning("Margin check — no price data from broker")
        return False, "margin check unavailable — no price data"

    check = mt5.order_check({
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": lot_size,
        "type": mt5.ORDER_TYPE_BUY,
        "price": tick.ask,
    })
    if check is None:
        logger.warning("Margin check — mt5.order_check() returned None")
        return False, "margin check unavailable — broker connection required"
    if check.retcode != 0:
        return False, f"insufficient margin (order_check retcode {check.retcode})"
    return True, ""


def check_minimum_stop_distance(
    direction: Direction,
    entry_price: float,
    sl_price: float,
) -> tuple[bool, str]:
    """Verify SL distance meets broker minimum stop distance (FR-007)."""
    sym = mt5.symbol_info(SYMBOL)
    if sym is None:
        logger.warning("Min-stop check — mt5.symbol_info() returned None")
        return False, "min-stop check unavailable — broker connection required"

    sl_distance_points = abs(entry_price - sl_price) / sym.point
    min_stop = sym.trade_stops_level

    if sl_distance_points < min_stop:
        return False, (
            f"SL distance below minimum — "
            f"{sl_distance_points:.1f} pts < {min_stop} pts minimum"
        )
    return True, ""


# ---------------------------------------------------------------------------
# T012 — preflight orchestrator
# ---------------------------------------------------------------------------

def run_preflight(
    exec_signal: ExecutionSignal,
    positions: dict[int, PositionState],
    day_start_equity: float,
    current_equity: float,
    config: dict,
    kill_switch_path: Optional[Path] = None,
) -> tuple[bool, str]:
    """Run all 5 checks in cheapest-first order; short-circuit on first failure (D-006).

    Order: kill-switch → pyramiding → drawdown → margin → min-stop.
    Returns (True, "") when all pass; (False, reason) on first failure.
    """
    # 1. Kill-switch — file read
    ok, reason = check_kill_switch(kill_switch_path)
    if not ok:
        return False, reason

    # 2. Pyramiding guard — in-memory dict, zero I/O
    ok, reason = check_existing_position(positions, exec_signal.entry_signal.direction)
    if not ok:
        return False, reason

    # 3. Daily drawdown — pure math, no MT5 call
    max_pct = config.get("risk", {}).get("max_daily_drawdown_pct", 5.0)
    ok, reason = check_daily_drawdown(day_start_equity, current_equity, max_pct)
    if not ok:
        return False, reason

    # 4. Margin sufficiency — MT5 API call
    ok, reason = check_margin_sufficiency(exec_signal.risk_calc.lot_size)
    if not ok:
        return False, reason

    # 5. Minimum stop distance — MT5 API call
    entry_price = (
        exec_signal.entry_signal.entry_zone_top
        + exec_signal.entry_signal.entry_zone_bottom
    ) / 2.0
    ok, reason = check_minimum_stop_distance(
        exec_signal.entry_signal.direction,
        entry_price,
        exec_signal.risk_calc.sl_price,
    )
    if not ok:
        return False, reason

    return True, ""
