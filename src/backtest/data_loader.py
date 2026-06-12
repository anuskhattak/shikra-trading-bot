"""Historical OHLCV CSV loader for the backtest engine — spec009 T015."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from src.analysis.models import OHLCVBar, Timeframe

_REQUIRED_COLS = {"date", "time", "open", "high", "low", "close"}


def load_ohlcv_csv(
    data_dir: str | Path,
    timeframe: Timeframe,
    symbol: str = "XAUUSD",
) -> list[OHLCVBar]:
    """Load OHLCV bars from a CSV file for the given timeframe.

    File path: {data_dir}/{symbol}_{timeframe.name}.csv
    Column names are matched case-insensitively; extra columns are ignored.
    Datetime is parsed from separate ``date`` and ``time`` columns
    using the format ``YYYY.MM.DD HH:MM`` (standard MT5 export format).
    Returns bars sorted oldest-first.

    Raises:
        FileNotFoundError: if the CSV file does not exist.
        ValueError: if any required column is absent.
    """
    path = Path(data_dir) / f"{symbol}_{timeframe.name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    bars: list[OHLCVBar] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"Empty or header-less CSV: {path}")

        # Build case-insensitive column map: lower(name) -> original name
        col_map: dict[str, str] = {c.lower().strip(): c for c in reader.fieldnames}

        missing = _REQUIRED_COLS - set(col_map)
        if missing:
            raise ValueError(f"Missing required columns {sorted(missing)} in {path}")

        # Accept either 'volume' or 'tick_volume' for the volume field
        vol_key: str | None = col_map.get("tick_volume") or col_map.get("volume")

        for row in reader:
            date_str = row[col_map["date"]].strip()
            time_str = row[col_map["time"]].strip()
            dt = datetime.strptime(
                f"{date_str} {time_str}", "%Y.%m.%d %H:%M"
            ).replace(tzinfo=timezone.utc)

            bars.append(OHLCVBar(
                open=float(row[col_map["open"]]),
                high=float(row[col_map["high"]]),
                low=float(row[col_map["low"]]),
                close=float(row[col_map["close"]]),
                volume=float(row[vol_key]) if vol_key else 0.0,
                timestamp=dt,
            ))

    return sorted(bars, key=lambda b: b.timestamp)
