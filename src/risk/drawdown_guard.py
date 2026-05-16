"""Daily drawdown guard — spec003 FR-012 to FR-015a.

Blocks all trading when daily equity loss exceeds the configured threshold.
Pure functions; all state returned explicitly (NFR-002, NFR-003).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from src.risk.models import RiskState, TradeAllowedResult

_RISK_LOG = Path("logs/risk_events.json")


def check_drawdown(
    day_start_equity: float,
    current_equity: float,
    max_pct: float,
) -> TradeAllowedResult:
    """Return TradeAllowedResult blocking trading when drawdown >= max_pct (FR-012, FR-014)."""
    dd = get_drawdown_pct(day_start_equity, current_equity)
    if dd >= max_pct:
        reason = f"Daily drawdown limit reached ({dd:.1f}% >= {max_pct:.1f}%)"
        _append_event({"event": "drawdown_blocked", "detail": reason, "drawdown_pct": dd})
        return TradeAllowedResult(allowed=False, reason=reason)
    return TradeAllowedResult(allowed=True, reason="not_blocked")


def reset_daily_state(state: RiskState, current_equity: float) -> RiskState:
    """Return new RiskState with day_start_equity reset and all daily counters cleared.

    Call at UTC 00:00. Session trade counters also reset — no intra-day session reset (FR-015).
    """
    from dataclasses import replace
    return replace(
        state,
        day_start_equity=current_equity,
        trades_today=0,
        session_trades={},
    )


def get_drawdown_pct(day_start_equity: float, current_equity: float) -> float:
    """Return drawdown as a positive percentage; 0.0 when equity >= start (FR-013)."""
    if day_start_equity <= 0:
        return 0.0
    loss = day_start_equity - current_equity
    return max(0.0, (loss / day_start_equity) * 100.0)


def _append_event(entry: dict) -> None:
    """Append a JSON event to logs/risk_events.json; silent fail on any write error (NFR-005)."""
    try:
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        with _RISK_LOG.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.error(f"risk_events.json write failed: {exc}")
