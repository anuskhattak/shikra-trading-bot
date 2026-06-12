"""Shared 4-stage trade evaluation pipeline — used identically by live and backtest modes.

No MetaTrader5 import anywhere in this file (FR-017, FR-003).
Never raises — all exceptions are caught and logged; caller always gets a PipelineContext back.
"""
from __future__ import annotations

import pandas as pd
from loguru import logger

from src.analysis.atr_service import ATRService
from src.analysis.h4_bias import H4BiasService
from src.analysis.models import OHLCVBar, Timeframe
from src.engine.models import Bias, Direction
from src.engine.smc_engine import generate_signal
from src.filters.models import FilterResult
from src.filters.trade_gate import evaluate_filters
from src.orchestrator.models import PipelineContext
from src.risk.lot_calculator import calculate_lot_size, calculate_sl_price, calculate_tp_prices
from src.risk.models import RiskCalculation


def _bars_to_df(bars: list[OHLCVBar]) -> pd.DataFrame:
    return pd.DataFrame([{
        "time":        b.timestamp,
        "open":        b.open,
        "high":        b.high,
        "low":         b.low,
        "close":       b.close,
        "tick_volume": b.volume,
    } for b in bars])


def run_pipeline(
    ctx: PipelineContext,
    atr_service: ATRService,
    config: dict,
    h4_bias_service: H4BiasService | None = None,
) -> PipelineContext:
    """Run 5 sequential pipeline stages and return the enriched PipelineContext.

    Stage 0 — H4 bias refresh: classify H4 structure; stores result in ctx.h4_bias_result.
    Stage 1 — ATR refresh: update cache for all timeframes in ctx.bars.
    Stage 2 — SMC detection: generate EntrySignal from H1 bars using live H4 bias.
    Stage 3 — Filter evaluation: session/spread/news/volatility gates.
    Stage 4 — Risk calculation: SL price, TP prices, lot size (technical only).

    Short-circuits on: ATR not ready, NONE signal, or BLOCKED filter.
    risk_calc is None whenever stage 4 is not reached.
    """
    risk_cfg = config.get("risk", {})

    # ── Stage 0: H4 bias refresh ────────────────────────────────────────────
    if h4_bias_service is not None:
        h4_bars = ctx.bars.get(Timeframe.H4, [])
        ctx.h4_bias_result = h4_bias_service.refresh(h4_bars)

    # ── Stage 1: ATR refresh ────────────────────────────────────────────────
    try:
        for tf, bars in ctx.bars.items():
            reading = atr_service.refresh(tf, bars)
            ctx.atr_readings[tf] = reading
    except Exception as exc:
        logger.error(f"[pipeline:{ctx.signal_id}] stage=ATR error={exc!r}")
        return ctx

    h1 = ctx.atr_readings.get(Timeframe.H1)
    if not h1 or h1.current_atr is None or h1.reference_atr is None:
        # Volatility filter and risk calc both need valid H1 ATR — abort early
        logger.debug(f"[pipeline:{ctx.signal_id}] H1 ATR not ready — skipping SMC and downstream stages")
        return ctx

    # ── Stage 2: SMC signal detection ───────────────────────────────────────
    try:
        df = _bars_to_df(ctx.bars.get(Timeframe.H1, []))
        htf_bias = ctx.h4_bias_result.bias if ctx.h4_bias_result is not None else Bias.NEUTRAL
        htf_bias_strength = ctx.h4_bias_result.strength if ctx.h4_bias_result is not None else 0.0
        ctx.entry_signal = generate_signal(
            df,
            htf_bias=htf_bias,
            htf_bias_strength=htf_bias_strength,
            config=config.get("smc_engine"),
        )
    except Exception as exc:
        logger.error(f"[pipeline:{ctx.signal_id}] stage=SMC error={exc!r}")
        return ctx

    if ctx.entry_signal is None or ctx.entry_signal.direction == Direction.NONE:
        logger.debug(f"[pipeline:{ctx.signal_id}] direction=NONE — skipping filters and risk calc")
        return ctx

    # ── Stage 3: Filter evaluation ──────────────────────────────────────────
    try:
        ctx.filter_result = evaluate_filters(
            signal_id=ctx.signal_id,
            now_utc=ctx.now_utc,
            spread_usd=ctx.spread_usd,
            news_events=ctx.news_events,
            current_atr=h1.current_atr,
            reference_atr=h1.reference_atr,
            config=config,
        )
    except Exception as exc:
        logger.error(f"[pipeline:{ctx.signal_id}] stage=filters error={exc!r}")
        return ctx

    if ctx.filter_result.final_result != FilterResult.ALLOWED:
        logger.debug(f"[pipeline:{ctx.signal_id}] signal BLOCKED — skipping risk calc")
        return ctx

    # ── Stage 4: Risk calculation (technical prices only) ───────────────────
    # State-based checks (drawdown, trade limits, recovery) are enforced by
    # ExecutionEngine.run_preflight() — not duplicated here (FR-005, D-001).
    try:
        d1 = ctx.atr_readings.get(Timeframe.D1)
        if not d1 or not d1.current_atr:
            logger.warning(f"[pipeline:{ctx.signal_id}] D1 ATR not ready — skipping risk calc")
            return ctx

        entry_price = (ctx.entry_signal.entry_zone_top + ctx.entry_signal.entry_zone_bottom) / 2.0
        sl_price = calculate_sl_price(
            entry_price,
            ctx.entry_signal.direction,
            d1.current_atr,
            risk_cfg.get("sl_atr_multiplier", 1.5),
        )
        sl_distance = abs(entry_price - sl_price)
        tp1_price, tp2_price = calculate_tp_prices(
            entry_price,
            sl_price,
            ctx.entry_signal.direction,
            risk_cfg.get("tp1_rr_ratio", 1.5),
            risk_cfg.get("tp2_rr_ratio", 3.0),
        )
        lot_size = calculate_lot_size(
            ctx.balance,
            risk_cfg.get("risk_percent", 1.0),
            sl_distance,
            risk_cfg.get("pip_value_per_lot", 10.0),
            risk_cfg.get("max_lot_size", 5.0),
            risk_cfg.get("min_lot_size", 0.01),
        )
        ctx.risk_calc = RiskCalculation(
            lot_size=lot_size,
            sl_price=sl_price,
            tp1_price=tp1_price,
            tp2_price=tp2_price,
            sl_distance=sl_distance,
            risk_amount_usd=ctx.balance * risk_cfg.get("risk_percent", 1.0) / 100.0,
            in_recovery=False,
            reason="pipeline_calc",
        )
    except Exception as exc:
        logger.error(f"[pipeline:{ctx.signal_id}] stage=risk error={exc!r}")

    return ctx
