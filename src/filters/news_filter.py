"""News filter — blocks trades during pre/post blackout windows around HIGH-impact events."""
import json
from datetime import datetime, timezone
from pathlib import Path

from src.filters.models import FilterDecision, FilterResult, NewsEvent, NewsImpact


def load_news_calendar(filepath: str) -> list[NewsEvent]:
    """Load and parse news events from JSON file. Returns [] on missing file, parse error, or bad schema."""
    try:
        path = Path(filepath)
        if not path.exists():
            return []
        with path.open() as f:
            data = json.load(f)
        events = []
        for item in data:
            events.append(NewsEvent(
                name=item["name"],
                impact=NewsImpact(item["impact"]),
                scheduled_utc=datetime.fromisoformat(item["scheduled_utc"].replace("Z", "+00:00")),
                currencies=item["currencies"],
            ))
        return events
    except Exception:
        return []


def check_news(now_utc: datetime, events: list[NewsEvent], config: dict) -> FilterDecision:
    """Gate trade on news calendar. Blocks during pre/post windows for configured impact levels."""
    news_cfg = config["filters"]["news"]
    pre_minutes = news_cfg["pre_event_minutes"]
    post_minutes = news_cfg["post_event_minutes"]
    impact_levels = {NewsImpact(lvl) for lvl in news_cfg["impact_levels"]}

    if not events:
        return FilterDecision(
            filter_name="news",
            result=FilterResult.BLOCKED,
            reason="NEWS_CALENDAR_UNAVAILABLE",
            metric_value=0.0,
            timestamp=now_utc,
        )

    for event in events:
        if event.impact not in impact_levels:
            continue
        # Positive delta → event is in the future; negative → event is in the past
        delta_minutes = (event.scheduled_utc - now_utc).total_seconds() / 60
        if 0 < delta_minutes <= pre_minutes:
            return FilterDecision(
                filter_name="news",
                result=FilterResult.BLOCKED,
                reason="NEWS_BLACKOUT_PRE_EVENT",
                metric_value=delta_minutes,
                timestamp=now_utc,
            )
        if -post_minutes <= delta_minutes <= 0:
            return FilterDecision(
                filter_name="news",
                result=FilterResult.BLOCKED,
                reason="NEWS_BLACKOUT_POST_EVENT",
                metric_value=abs(delta_minutes),
                timestamp=now_utc,
            )

    return FilterDecision(
        filter_name="news",
        result=FilterResult.ALLOWED,
        reason="ALLOWED",
        metric_value=0.0,
        timestamp=now_utc,
    )
