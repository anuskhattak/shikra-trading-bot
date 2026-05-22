"""Unit tests for src/execution/audit_logger.py."""

import json
import threading
from pathlib import Path

import pytest

from src.execution.audit_logger import write_audit_entries, write_audit_entry
from src.execution.models import AuditAction, TradeAuditEntry


def _entry(action: AuditAction, audit_id: str = "aud-001") -> TradeAuditEntry:
    return TradeAuditEntry(
        audit_id=audit_id,
        timestamp_utc="2026-05-20T10:00:00Z",
        action_type=action,
        signal_id="sig-test",
    )


@pytest.fixture
def log_path(tmp_path) -> Path:
    return tmp_path / "trades.json"


class TestAllAuditActions:
    def test_all_8_action_types_produce_valid_entries(self, log_path):
        for i, action in enumerate(AuditAction):
            write_audit_entry(_entry(action, f"aud-{i:03}"), log_path)

        records = json.loads(log_path.read_text())
        assert len(records) == 8
        stored_types = {r["action_type"] for r in records}
        assert stored_types == {a.value for a in AuditAction}

    def test_enum_serialised_as_string_not_dict(self, log_path):
        write_audit_entry(_entry(AuditAction.ORDER_PLACED), log_path)
        records = json.loads(log_path.read_text())
        assert isinstance(records[0]["action_type"], str)
        assert records[0]["action_type"] == "ORDER_PLACED"


class TestWriteFailureSafety:
    def test_ioerror_does_not_raise(self, tmp_path):
        """FR-018: write failures must never surface to caller."""
        blocker = tmp_path / "blocked_dir"
        blocker.write_text("I am a file, not a dir")
        bad_path = blocker / "trades.json"  # parent is a file → mkdir fails
        write_audit_entry(_entry(AuditAction.ORDER_PLACED), bad_path)  # Must not raise


class TestAppendBehaviour:
    def test_multiple_entries_appended_not_overwritten(self, log_path):
        write_audit_entry(_entry(AuditAction.ORDER_PLACED, "a1"), log_path)
        write_audit_entry(_entry(AuditAction.ORDER_REJECTED, "a2"), log_path)

        records = json.loads(log_path.read_text())
        assert len(records) == 2
        assert records[0]["audit_id"] == "a1"
        assert records[1]["audit_id"] == "a2"

    def test_write_audit_entries_batch_appends_atomically(self, log_path):
        batch = [_entry(AuditAction.PARTIAL_CLOSE, f"b{i}") for i in range(3)]
        write_audit_entries(batch, log_path)

        records = json.loads(log_path.read_text())
        assert len(records) == 3

    def test_empty_entries_list_writes_nothing(self, log_path):
        write_audit_entries([], log_path)
        assert not log_path.exists()

    def test_corrupt_existing_file_restarts_fresh(self, log_path):
        log_path.write_text("not json{{", encoding="utf-8")
        write_audit_entry(_entry(AuditAction.ORDER_REJECTED, "x"), log_path)
        records = json.loads(log_path.read_text())
        assert len(records) == 1


class TestConcurrentWrites:
    def test_two_threads_do_not_corrupt_json_array(self, log_path):
        """AUDIT_LOG_LOCK must prevent interleaved writes from corrupting the file."""
        errors: list[Exception] = []

        def write_batch(thread_id: int) -> None:
            try:
                for i in range(10):
                    write_audit_entry(
                        _entry(AuditAction.TRAILING_STOP_UPDATED, f"t{thread_id}-{i}"),
                        log_path,
                    )
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=write_batch, args=(1,))
        t2 = threading.Thread(target=write_batch, args=(2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors
        records = json.loads(log_path.read_text())
        assert len(records) == 20
