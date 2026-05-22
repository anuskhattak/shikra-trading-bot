"""Unit tests for src/execution/kill_switch.py."""

import json
from pathlib import Path

import pytest

from src.execution.kill_switch import (
    activate_kill_switch,
    deactivate_kill_switch,
    is_kill_switch_active,
)


@pytest.fixture
def ks_path(tmp_path) -> Path:
    return tmp_path / "kill_switch.json"


class TestIsKillSwitchActive:
    def test_file_absent_returns_false(self, ks_path):
        assert is_kill_switch_active(ks_path) is False

    def test_malformed_json_returns_false(self, ks_path):
        ks_path.write_text("not valid json{{", encoding="utf-8")
        assert is_kill_switch_active(ks_path) is False

    def test_active_false_in_file_returns_false(self, ks_path):
        ks_path.write_text(json.dumps({"active": False}), encoding="utf-8")
        assert is_kill_switch_active(ks_path) is False

    def test_missing_active_key_returns_false(self, ks_path):
        ks_path.write_text(json.dumps({"activated_by": "someone"}), encoding="utf-8")
        assert is_kill_switch_active(ks_path) is False


class TestActivateDeactivate:
    def test_activate_makes_active_true(self, ks_path):
        activate_kill_switch(ks_path)
        assert is_kill_switch_active(ks_path) is True

    def test_deactivate_makes_active_false(self, ks_path):
        activate_kill_switch(ks_path)
        deactivate_kill_switch(ks_path)
        assert is_kill_switch_active(ks_path) is False

    def test_activate_writes_valid_json_with_operator(self, ks_path):
        activate_kill_switch(ks_path, activated_by="operator-A")
        data = json.loads(ks_path.read_text(encoding="utf-8"))
        assert data["active"] is True
        assert data["activated_by"] == "operator-A"
        assert data["activated_at"] is not None

    def test_activate_without_operator_writes_valid_json(self, ks_path):
        activate_kill_switch(ks_path)
        data = json.loads(ks_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert data["active"] is True

    def test_deactivate_without_prior_activate_does_not_raise(self, ks_path):
        deactivate_kill_switch(ks_path)
        assert is_kill_switch_active(ks_path) is False

    def test_multiple_activate_calls_idempotent(self, ks_path):
        activate_kill_switch(ks_path)
        activate_kill_switch(ks_path)
        assert is_kill_switch_active(ks_path) is True

    def test_activate_deactivate_full_cycle(self, ks_path):
        assert is_kill_switch_active(ks_path) is False
        activate_kill_switch(ks_path)
        assert is_kill_switch_active(ks_path) is True
        deactivate_kill_switch(ks_path)
        assert is_kill_switch_active(ks_path) is False
