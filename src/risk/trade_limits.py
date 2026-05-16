"""Trade limit enforcement — spec003 FR-016 to FR-022.

Checks daily trade cap, session trade cap, and post-SL cooldown period.
Pure functions; all state returned explicitly (NFR-002, NFR-003).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from src.risk.models import RiskState, TradeAllowedResult


def is_trade_limit_allowed(
    state: RiskState,
    config: SimpleNamespace,
    current_time: datetime,
    session: str,
) -> TradeAllowedResult:
    """Return TradeAllowedResult; checks daily → session → cooldown in order (FR-016–FR-019)."""
    if state.trades_today >= config.max_trades_per_day:
        return TradeAllowedResult(
            allowed=False,
            reason=f"Daily trade limit reached ({state.trades_today}/{config.max_trades_per_day})",
        )

    session_count = state.session_trades.get(session, 0)
    if session_count >= config.max_trades_per_session:
        return TradeAllowedResult(
            allowed=False,
            reason=f"Session trade limit reached ({session_count}/{config.max_trades_per_session}) for {session}",
        )

    if state.last_sl_time is not None:
        elapsed = current_time - state.last_sl_time
        cooldown = timedelta(hours=config.cooldown_after_sl_hours)
        if elapsed < cooldown:
            remaining = cooldown - elapsed
            return TradeAllowedResult(
                allowed=False,
                reason=f"Cooldown active after SL hit — {remaining} remaining",
            )

    return TradeAllowedResult(allowed=True, reason="not_blocked")


def record_trade_opened(state: RiskState, session: str) -> RiskState:
    """Return new RiskState with trades_today and session_trades incremented (FR-020)."""
    from dataclasses import replace
    new_session = {**state.session_trades, session: state.session_trades.get(session, 0) + 1}
    return replace(state, trades_today=state.trades_today + 1, session_trades=new_session)


def record_sl_hit(state: RiskState, current_time: datetime) -> RiskState:
    """Return new RiskState with last_sl_time set and consecutive_losses incremented (FR-021)."""
    from dataclasses import replace
    return replace(
        state,
        last_sl_time=current_time,
        consecutive_losses=state.consecutive_losses + 1,
    )


def record_trade_won(state: RiskState) -> RiskState:
    """Return new RiskState with consecutive_losses reset to 0 (FR-022)."""
    from dataclasses import replace
    return replace(state, consecutive_losses=0)
