"""Thread-safe audit logger — appends TradeAuditEntry records to logs/trades.json.

Single module-level lock (AUDIT_LOG_LOCK) owns all writes to the audit file.
Write failures are silently swallowed — trade execution must never be blocked
by a logging failure (FR-018).
"""

import json
import sys
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Sequence

from src.execution.models import TradeAuditEntry

AUDIT_LOG_PATH = Path("logs/trades.json")
AUDIT_LOG_LOCK = threading.Lock()


def write_audit_entry(entry: TradeAuditEntry, path: Optional[Path] = None) -> None:
    """Append a single TradeAuditEntry to the audit log."""
    write_audit_entries([entry], path)


def write_audit_entries(
    entries: Sequence[TradeAuditEntry], path: Optional[Path] = None
) -> None:
    """Append multiple TradeAuditEntry records under a single lock acquisition."""
    if not entries:
        return

    resolved = path if path is not None else AUDIT_LOG_PATH
    serialised = [_serialise(e) for e in entries]

    try:
        with AUDIT_LOG_LOCK:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            records: list = []
            if resolved.exists() and resolved.stat().st_size > 0:
                try:
                    records = json.loads(resolved.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    pass  # Corrupt file — restart array rather than blocking trades
            records.extend(serialised)
            resolved.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")
    except OSError as exc:
        print(f"[audit_logger] write failed — {exc}", file=sys.stderr)


def _serialise(entry: TradeAuditEntry) -> dict:
    raw = asdict(entry)
    raw["action_type"] = entry.action_type.value  # Enum → string for JSON
    return raw
