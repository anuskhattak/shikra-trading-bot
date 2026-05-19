"""Spread filter — blocks trades when XAUUSD spread exceeds the configured USD threshold."""
from datetime import datetime, timezone

from src.filters.models import FilterDecision, FilterResult


def check_spread(spread_usd: float, config: dict) -> FilterDecision:
    """Gate trade on current spread (USD). Blocks if spread > max_spread_usd or invalid (≤ 0)."""
    now = datetime.now(timezone.utc)
    max_spread = config["filters"]["spread"]["max_spread_usd"]

    if spread_usd <= 0:
        return FilterDecision(
            filter_name="spread",
            result=FilterResult.BLOCKED,
            reason="INVALID_SPREAD",
            metric_value=spread_usd,
            timestamp=now,
        )

    if spread_usd > max_spread:
        return FilterDecision(
            filter_name="spread",
            result=FilterResult.BLOCKED,
            reason="SPREAD_TOO_WIDE",
            metric_value=spread_usd,
            timestamp=now,
        )

    return FilterDecision(
        filter_name="spread",
        result=FilterResult.ALLOWED,
        reason="ALLOWED",
        metric_value=spread_usd,
        timestamp=now,
    )
