"""Recovery mode management — spec003 FR-023 to FR-028.

Activates after N consecutive SL hits; reduces lot size and filters low-confidence
signals until the system recovers the target pip amount.
Pure functions; all state returned explicitly (NFR-002, NFR-003).
"""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from loguru import logger

from src.risk.models import RiskState

_RISK_LOG = Path("logs/risk_events.json")


def check_recovery_status(state: RiskState, config: SimpleNamespace) -> RiskState:
    """Activate or exit recovery mode based on losses and profit target (FR-023, FR-026, FR-027)."""
    if state.in_recovery_mode:
        if state.recovery_profit_pips >= config.recovery_profit_target_pips:
            _append_event({
                "event": "recovery_exit",
                "recovery_profit_pips": state.recovery_profit_pips,
                "target": config.recovery_profit_target_pips,
            })
            return replace(state, in_recovery_mode=False, recovery_profit_pips=0.0)
        return state

    if state.consecutive_losses >= config.max_consecutive_losses:
        _append_event({
            "event": "recovery_enter",
            "consecutive_losses": state.consecutive_losses,
            "threshold": config.max_consecutive_losses,
        })
        return replace(state, in_recovery_mode=True, recovery_profit_pips=0.0)

    return state


def is_signal_allowed_in_recovery(confidence: float, recovery_min_confidence: float) -> bool:
    """Return False when confidence is below the recovery threshold (FR-025)."""
    return confidence >= recovery_min_confidence


def apply_recovery_lot(lot_size: float, recovery_lot_multiplier: float) -> float:
    """Return lot_size × recovery_lot_multiplier; called before final clamping (FR-024)."""
    return lot_size * recovery_lot_multiplier


def update_recovery_profit(state: RiskState, pips_gained_price_units: float) -> RiskState:
    """Return new RiskState with recovery_profit_pips incremented (FR-026, FR-028).

    Called by spec004 (Execution Engine) after each closed trade.
    """
    return replace(
        state,
        recovery_profit_pips=state.recovery_profit_pips + pips_gained_price_units,
    )


def _append_event(entry: dict) -> None:
    """Append a JSON event to logs/risk_events.json; silent fail on any write error (NFR-005)."""
    try:
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        with _RISK_LOG.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.error(f"risk_events.json write failed: {exc}")
