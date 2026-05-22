"""Kill-switch — atomic file-based halt for new order placement.

File absent → False (safe default). Corrupt JSON → False (safe default, ADR-0001).
Writes use temp-file + rename to prevent partial reads during write.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.execution.models import KillSwitchState

KILL_SWITCH_PATH = Path("logs/kill_switch.json")


def activate_kill_switch(
    path: Path = KILL_SWITCH_PATH,
    activated_by: Optional[str] = None,
) -> None:
    """Atomically write an active KillSwitchState to disk."""
    _write_atomic(
        KillSwitchState(active=True, activated_at=datetime.utcnow(), activated_by=activated_by),
        path,
    )


def deactivate_kill_switch(path: Path = KILL_SWITCH_PATH) -> None:
    """Atomically write an inactive KillSwitchState to disk."""
    _write_atomic(KillSwitchState(active=False), path)


def is_kill_switch_active(path: Path = KILL_SWITCH_PATH) -> bool:
    """Return True only when the kill-switch file exists and active == True."""
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("active", False))
    except (json.JSONDecodeError, OSError):
        return False


def _write_atomic(state: KillSwitchState, path: Path) -> None:
    """Write via temp file + Path.replace() — atomic on POSIX, best-effort on Windows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "active": state.active,
        "activated_at": state.activated_at.isoformat() if state.activated_at else None,
        "activated_by": state.activated_by,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
