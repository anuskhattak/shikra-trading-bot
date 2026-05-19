"""Public API for the src.filters package."""
from src.filters.models import FilterDecision, FilterResult, TradeGateResult
from src.filters.news_filter import load_news_calendar
from src.filters.trade_gate import evaluate_filters

__all__ = [
    "evaluate_filters",
    "load_news_calendar",
    "TradeGateResult",
    "FilterDecision",
    "FilterResult",
]
