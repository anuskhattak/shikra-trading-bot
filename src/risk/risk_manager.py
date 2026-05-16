"""Risk orchestrator — spec003 D-006, NFR-006.

Single entry point for all risk checks. Calls sub-modules in order:
direction guard → drawdown → trade limits → recovery → lot/SL/TP assembly.
Pure functional update pattern: returns new RiskState, never mutates input (NFR-003).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from loguru import logger

from src.engine.models import Direction, EntrySignal
from src.risk.drawdown_guard import check_drawdown
from src.risk.lot_calculator import calculate_lot_size, calculate_sl_price, calculate_tp_prices
from src.risk.models import RiskCalculation, RiskState
from src.risk.recovery_mode import (
    apply_recovery_lot,
    check_recovery_status,
    is_signal_allowed_in_recovery,
)
from src.risk.trade_limits import is_trade_limit_allowed

_RISK_LOG = Path("logs/risk_events.json")
_SESSION = "DEFAULT"

_DEFAULTS = dict(
    risk_percent=1.0,
    max_lot_size=5.0,
    min_lot_size=0.01,
    pip_value_per_lot=10.0,
    sl_atr_multiplier=1.5,
    tp1_rr_ratio=1.5,
    tp2_rr_ratio=3.0,
    max_daily_drawdown=5.0,
    max_trades_per_day=5,
    max_trades_per_session=2,
    cooldown_after_sl_hours=2.0,
    max_consecutive_losses=3,
    recovery_lot_multiplier=0.5,
    recovery_min_confidence=0.80,
    recovery_profit_target_pips=50.0,
)


def evaluate_trade_risk(
    entry_signal: EntrySignal,
    balance: float,
    current_equity: float,
    d1_atr: float,
    state: RiskState,
    config: dict | SimpleNamespace | None = None,
) -> tuple[RiskCalculation, RiskState]:
    """Main entry point. Returns (RiskCalculation, updated_state).

    Never raises on valid inputs. Returns zero_risk_calc (lot=0.0) when blocked.
    On allowed=True: appends DEBUG entry to logs/risk_events.json (NFR-006).
    """
    cfg = _resolve_config(config)
    current_time = datetime.now(timezone.utc)

    def _zero(reason: str) -> tuple[RiskCalculation, RiskState]:
        return _zero_risk_calc(reason, state.in_recovery_mode), state

    # 1 — Direction guard
    if entry_signal.direction == Direction.NONE:
        return _zero("direction=NONE")

    # 2 — Drawdown check
    dd_result = check_drawdown(state.day_start_equity, current_equity, cfg.max_daily_drawdown)
    if not dd_result.allowed:
        return _zero(dd_result.reason)

    # 3 — Trade limits check
    limit_result = is_trade_limit_allowed(state, cfg, current_time, _SESSION)
    if not limit_result.allowed:
        return _zero(limit_result.reason)

    # 4 — Recovery status update
    state = check_recovery_status(state, cfg)

    # 5 — Recovery confidence gate
    if state.in_recovery_mode:
        if not is_signal_allowed_in_recovery(entry_signal.confidence, cfg.recovery_min_confidence):
            return _zero(
                f"Signal confidence {entry_signal.confidence:.2f} below recovery minimum {cfg.recovery_min_confidence:.2f}"
            )

    # 6 — Price calculations
    entry_price = (entry_signal.entry_zone_top + entry_signal.entry_zone_bottom) / 2.0
    sl_price = calculate_sl_price(entry_price, entry_signal.direction, d1_atr, cfg.sl_atr_multiplier)
    sl_distance = abs(entry_price - sl_price)

    # 7 — Lot size (apply recovery multiplier before final clamp)
    lot = calculate_lot_size(
        balance, cfg.risk_percent, sl_distance,
        cfg.pip_value_per_lot, cfg.max_lot_size, cfg.min_lot_size,
    )
    if state.in_recovery_mode:
        lot = apply_recovery_lot(lot, cfg.recovery_lot_multiplier)
        lot = max(cfg.min_lot_size, round(lot, 2))

    # 8 — TP prices
    tp1_price, tp2_price = calculate_tp_prices(
        entry_price, sl_price, entry_signal.direction, cfg.tp1_rr_ratio, cfg.tp2_rr_ratio,
    )

    risk_amount_usd = lot * sl_distance * cfg.pip_value_per_lot
    risk_calc = RiskCalculation(
        lot_size=lot,
        sl_price=sl_price,
        tp1_price=tp1_price,
        tp2_price=tp2_price,
        sl_distance=sl_distance,
        risk_amount_usd=risk_amount_usd,
        in_recovery=state.in_recovery_mode,
        reason="ALLOWED",
    )

    _log_allowed(risk_calc)
    return risk_calc, state


def _zero_risk_calc(reason: str, in_recovery: bool) -> RiskCalculation:
    """Return zero RiskCalculation when trade is blocked (contracts/risk_manager.md)."""
    return RiskCalculation(
        lot_size=0.0,
        sl_price=0.0,
        tp1_price=0.0,
        tp2_price=0.0,
        sl_distance=0.0,
        risk_amount_usd=0.0,
        in_recovery=in_recovery,
        reason=reason,
    )


def _resolve_config(config: dict | SimpleNamespace | None) -> SimpleNamespace:
    """Convert dict or None config to SimpleNamespace with defaults filled in."""
    if config is None:
        return SimpleNamespace(**_DEFAULTS)
    if isinstance(config, dict):
        merged = {**_DEFAULTS, **config}
        return SimpleNamespace(**merged)
    return config


def _log_allowed(risk_calc: RiskCalculation) -> None:
    """Append DEBUG entry to logs/risk_events.json on allowed trade (NFR-006); silent fail."""
    try:
        entry = {
            "event": "evaluate_trade_risk",
            "level": "DEBUG",
            "lot_size": risk_calc.lot_size,
            "sl_price": risk_calc.sl_price,
            "tp1_price": risk_calc.tp1_price,
            "tp2_price": risk_calc.tp2_price,
            "max_loss_usd": risk_calc.risk_amount_usd,
            "reason": "ALLOWED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with _RISK_LOG.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.error(f"risk_events.json write failed: {exc}")
