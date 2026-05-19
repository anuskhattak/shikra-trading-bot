"""Trade gate orchestrator — runs all 4 filters in sequence; short-circuit, fail-safe, logging."""
import json
from datetime import datetime, timezone
from pathlib import Path

from src.filters.models import FilterDecision, FilterResult, NewsEvent, TradeGateResult
from src.filters.news_filter import check_news
from src.filters.session_filter import check_session
from src.filters.spread_filter import check_spread
from src.filters.volatility_filter import check_volatility


def _log_result(result: TradeGateResult, config: dict) -> None:
    """Append TradeGateResult as newline-delimited JSON to filters_log. Silent on any error."""
    try:
        log_path = Path(config["logging"]["filters_log"])
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "signal_id": result.signal_id,
            "final_result": result.final_result.value,
            "evaluated_at": result.evaluated_at.isoformat(),
            "decisions": [
                {
                    "filter_name": d.filter_name,
                    "result": d.result.value,
                    "reason": d.reason,
                    "metric_value": d.metric_value,
                    "timestamp": d.timestamp.isoformat(),
                }
                for d in result.decisions
            ],
        }
        with log_path.open("a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception:
        pass


def evaluate_filters(
    signal_id: str,
    now_utc: datetime,
    spread_usd: float,
    news_events: list[NewsEvent],
    current_atr: float,
    reference_atr: float,
    config: dict,
) -> TradeGateResult:
    """Run session → spread → news → volatility filters. Short-circuit on first BLOCKED.

    Each filter is wrapped in try/except — any exception → BLOCKED with reason FILTER_ERROR (FR-015).
    Every call produces a logged TradeGateResult (FR-012). Caller supplies signal_id as UUID string.
    """
    decisions: list[FilterDecision] = []

    _filters = [
        ("session",    check_session,    (now_utc, config)),
        ("spread",     check_spread,     (spread_usd, config)),
        ("news",       check_news,       (now_utc, news_events, config)),
        ("volatility", check_volatility, (current_atr, reference_atr, config)),
    ]

    for name, fn, args in _filters:
        try:
            decision = fn(*args)
        except Exception as exc:
            decision = FilterDecision(
                filter_name=name,
                result=FilterResult.BLOCKED,
                reason="FILTER_ERROR",
                metric_value=str(exc),
                timestamp=datetime.now(timezone.utc),
            )
        decisions.append(decision)
        if decision.result == FilterResult.BLOCKED:
            break

    final = (
        FilterResult.ALLOWED
        if all(d.result == FilterResult.ALLOWED for d in decisions)
        else FilterResult.BLOCKED
    )

    result = TradeGateResult(
        signal_id=signal_id,
        final_result=final,
        decisions=decisions,
        evaluated_at=now_utc,
    )
    _log_result(result, config)
    return result
