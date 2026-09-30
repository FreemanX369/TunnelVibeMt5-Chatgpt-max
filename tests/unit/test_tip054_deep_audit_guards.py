"""Regression coverage for concrete durable-run and source guard audit defects."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json

import pytest

from vibemql5.backend_admin.core import BackendAdmin
from vibemql5.core.facade import ToolFacade


def _source(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/terminals.json").write_text('{"terminals": []}')
    path = tmp_path / "workspaces/demo/Experts/DemoEA.mq5"
    path.parent.mkdir(parents=True)
    path.write_text("// before\n")
    facade = ToolFacade(tmp_path)
    sha = facade.get_source_hash("demo", "Experts/DemoEA.mq5")["sha256"]
    return facade, path, sha


def test_durable_spawn_failure_is_terminal_and_idempotent(tmp_path, monkeypatch):
    admin = BackendAdmin(tmp_path)
    calls = []
    def fail(*args, **kwargs):
        calls.append(args)
        raise OSError("controlled spawn failure")
    monkeypatch.setattr("vibemql5.backend_admin.core.subprocess.Popen", fail)
    first = admin.start_test_run("unit", "AUDIT/SPAWN/FAIL")
    assert first["state"] == "FAILED"
    assert first["reason_code"] == "TEST_WORKER_START_FAILED"
    assert first["finished_at_utc"]
    assert first["worker_pid"] is None
    assert admin.get_test_run(first["run_id"])["result"]["exception_type"] == "OSError"
    replay = admin.start_test_run("unit", "AUDIT/SPAWN/FAIL")
    assert replay["state"] == "FAILED" and replay["idempotent_recovered"] is True
    assert len(calls) == 1


@pytest.mark.parametrize("operation", ["write", "patch"])
@pytest.mark.parametrize("checkpoint_kind", ["fabricated", "wrong_path", "old_version", "corrupted"])
def test_source_mutation_rejects_unbound_checkpoint(tmp_path, operation, checkpoint_kind):
    facade, path, sha = _source(tmp_path)
    if checkpoint_kind == "fabricated":
        checkpoint = "CP-20260101-000000-AAAAAAAAAAAA"
    elif checkpoint_kind == "wrong_path":
        other = path.with_name("OtherEA.mq5")
        other.write_bytes(path.read_bytes())
        checkpoint = facade.create_checkpoint("demo", "Experts/OtherEA.mq5")["checkpoint_id"]
    else:
        checkpoint = facade.create_checkpoint("demo", "Experts/DemoEA.mq5")["checkpoint_id"]
        if checkpoint_kind == "old_version":
            path.write_text("// modified after checkpoint\n")
            sha = facade.get_source_hash("demo", "Experts/DemoEA.mq5")["sha256"]
        else:
            (facade.revisions._checkpoint_dir("demo", checkpoint) / "source.bin").write_bytes(b"tampered")
    before = path.read_bytes()
    with pytest.raises((ValueError, FileNotFoundError)):
        if operation == "write":
            facade.write_source("demo", "Experts/DemoEA.mq5", "// after\n", sha, checkpoint)
        else:
            facade.apply_patch("demo", "Experts/DemoEA.mq5", [{"old": "//", "new": "/*"}], sha, checkpoint)
    assert path.read_bytes() == before


def test_new_source_guard_is_rechecked_under_mutation_lease(tmp_path, monkeypatch):
    facade, path, sha = _source(tmp_path)
    target = path.with_name("RaceEA.mq5")
    @contextmanager
    def acquired_after_other_creator(*args, **kwargs):
        target.write_text("// other client created this\n")
        yield
    monkeypatch.setattr(facade.concurrency, "mutation", acquired_after_other_creator)
    with pytest.raises(ValueError, match="MULTI_CLIENT_CAS_REQUIRED"):
        facade.write_source("demo", "Experts/RaceEA.mq5", "// should not overwrite\n")
    assert target.read_text() == "// other client created this\n"


@pytest.mark.parametrize("completion_kind", ["stale", "current", "recovered", "unrelated"])
def test_soak_completion_requires_exact_run_and_build_binding(tmp_path, monkeypatch, completion_kind):
    admin = BackendAdmin(tmp_path)
    state_path = tmp_path / "soak.json"
    recovered = completion_kind == "recovered"
    started = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat() if recovered else None
    monkeypatch.setattr(admin, "run_tests", lambda suite: {
        "status": "STARTED", "state_path": str(state_path), "bridge_build": "TIP-053",
        "recovered": recovered, "soak_run_id": "SOAK-OWN", "soak_started_at_utc": started,
    })
    first = admin.start_test_run("tip033_soak", "AUDIT/SOAK/" + completion_kind)
    actual_start = started or (datetime.now(timezone.utc) + timedelta(milliseconds=1)).isoformat()
    payload = {
        "last_status": "PASS", "current_runtime_certification": True,
        "bridge_build": "TIP-053", "run_id": "SOAK-OWN",
        "last_result": {"started_at_utc": actual_start},
    }
    if completion_kind == "stale":
        payload["bridge_build"] = "OLD-BUILD"
        payload["last_result"]["started_at_utc"] = "2000-01-01T00:00:00Z"
    elif completion_kind == "unrelated":
        payload["run_id"] = "SOAK-SOMEONE-ELSE"
    state_path.write_text(json.dumps(payload))
    out = admin.get_test_run(first["run_id"])
    assert out["state"] == ("PASSED" if completion_kind in {"current", "recovered"} else "RUNNING")
    assert out["soak_state_status"] == ("VERIFIED_RUN_BINDING" if out["state"] == "PASSED" else "UNVERIFIED_RUN_BINDING")


def test_soak_start_failure_does_not_leave_starting_receipt(tmp_path, monkeypatch):
    admin = BackendAdmin(tmp_path)
    def fail(suite):
        raise OSError("controlled soak spawn failure")
    monkeypatch.setattr(admin, "run_tests", fail)
    first = admin.start_test_run("tip033_soak", "AUDIT/SOAK/FAIL")
    assert first["state"] == "FAILED"
    assert admin.get_test_run(first["run_id"])["reason_code"] == "TEST_WORKER_START_FAILED"
