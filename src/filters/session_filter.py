"""Session filter — classifies current UTC time into trading session and gates trades."""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import holidays

from src.filters.models import FilterDecision, FilterResult, SessionLabel, SessionWindow


def _parse_windows(config: dict) -> list[SessionWindow]:
    """Build SessionWindow list from config sessions: block, skipping disabled entries."""
    windows = []
    for name, cfg in config.get("sessions", {}).items():
        if cfg.get("enabled", True):
            windows.append(SessionWindow(
                name=name,
                local_open=cfg["local_open"],
                local_close=cfg["local_close"],
                timezone=cfg["timezone"],
                enabled=True,
            ))
    return windows


def _is_in_window(now_utc: datetime, window: SessionWindow) -> bool:
    """True if now_utc falls in [local_open, local_close) for the given window (DST-aware)."""
    tz = ZoneInfo(window.timezone)
    now_local = now_utc.astimezone(tz)
    h_open, m_open = map(int, window.local_open.split(":"))
    h_close, m_close = map(int, window.local_close.split(":"))
    t = now_local.time()
    return time(h_open, m_open) <= t < time(h_close, m_close)


def get_current_session(now_utc: datetime, config: dict) -> SessionLabel:
    """Classify current UTC time into a trading session label.

    now_utc must be UTC-aware. Weekends and GB public holidays → CLOSED.
    Asian window 00:00–07:00 UTC → ASIAN. Post-NY gap 21:00–00:00 UTC → CLOSED.
    London/NY detected via local [08:00, 17:00) windows with IANA DST handling.
    """
    if now_utc.weekday() >= 5:  # Saturday=5, Sunday=6
        return SessionLabel.CLOSED

    gb_holidays = holidays.country_holidays("GB")
    if now_utc.date() in gb_holidays:
        return SessionLabel.CLOSED

    windows = _parse_windows(config)
    london_open = any(w.name == "london" and _is_in_window(now_utc, w) for w in windows)
    ny_open = any(w.name == "new_york" and _is_in_window(now_utc, w) for w in windows)

    if london_open and ny_open:
        return SessionLabel.LONDON_NY_OVERLAP
    if london_open:
        return SessionLabel.LONDON
    if ny_open:
        return SessionLabel.NEW_YORK

    # Asian window: 00:00–07:00 UTC (exclusive end)
    if 0 <= now_utc.hour < 7:
        return SessionLabel.ASIAN

    # All other times (07:xx pre-London gap, post-NY gap 21:00–00:00)
    return SessionLabel.CLOSED


def check_session(now_utc: datetime, config: dict) -> FilterDecision:
    """Gate trade on current session. ALLOWED for London/NY/Overlap; BLOCKED otherwise."""
    label = get_current_session(now_utc, config)
    allowed = {SessionLabel.LONDON, SessionLabel.NEW_YORK, SessionLabel.LONDON_NY_OVERLAP}

    if label in allowed:
        return FilterDecision(
            filter_name="session",
            result=FilterResult.ALLOWED,
            reason="ALLOWED",
            metric_value=label.value,
            timestamp=now_utc,
        )

    reason = "ASIAN_SESSION_EXCLUDED" if label == SessionLabel.ASIAN else "MARKET_CLOSED"
    return FilterDecision(
        filter_name="session",
        result=FilterResult.BLOCKED,
        reason=reason,
        metric_value=label.value,
        timestamp=now_utc,
    )
