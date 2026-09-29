from __future__ import annotations

import json
import os
from types import SimpleNamespace

from vibemql5.backend_admin.core import BackendAdmin


def _root(tmp_path):
    root = tmp_path
    (root / "app" / "vibemql5").mkdir(parents=True)
    (root / "config").mkdir(parents=True)
    (root / "config" / "settings.json").write_text(json.dumps({
        "resource_guard": {},
        "retention": {"completed_jobs": 20},
        "jobs": {},
    }), encoding="utf-8")
    (root / "config" / "build-provenance.json").write_text(json.dumps({
        "schema_version": "1.0",
        "bridge_build": "TIP-053",
        "bridge_version": "0.2.42",
    }), encoding="utf-8")
    return root


def test_describe_capabilities_exposes_allowed_suites(tmp_path):
    admin = BackendAdmin(_root(tmp_path))
    out = admin.describe_capabilities()
    assert out["status"] == "PASS"
    assert "unit" in out["test_suites"]
    assert "tip033_soak" in out["test_suites"]
    assert out["backend_read_file"]["max_bytes_semantics"].startswith("whole-file")


def test_read_file_too_large_is_structured_block(tmp_path):
    root = _root(tmp_path)
    path = root / "app" / "vibemql5" / "large.py"
    path.write_text("x" * 20, encoding="utf-8")
    out = BackendAdmin(root).read_file("app/vibemql5/large.py", max_bytes=4)
    assert out == {
        "status": "BLOCKED",
        "reason_code": "FILE_TOO_LARGE",
        "path": str(path.resolve()),
        "bytes": 20,
        "max_bytes": 4,
    }


def test_invalid_test_suite_returns_allowed_values(tmp_path):
    admin = BackendAdmin(_root(tmp_path))
    out = admin.run_tests("smoke")
    assert out["status"] == "BLOCKED"
    assert out["reason_code"] == "TEST_SUITE_NOT_ALLOWED"
    assert "unit" in out["allowed_suites"]


def test_baseline_aware_framework_error_cannot_pass(tmp_path, monkeypatch):
    admin = BackendAdmin(_root(tmp_path))
    monkeypatch.setattr(
        admin,
        "_run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=5, stdout="", stderr="usage error"),
    )
    out = admin.run_tests("baseline_aware")
    assert out["status"] == "FAIL"
    assert out["framework_completed"] is False
    assert out["baseline_conformant"] is False


def test_durable_test_operation_is_idempotent(tmp_path, monkeypatch):
    admin = BackendAdmin(_root(tmp_path))
    monkeypatch.setattr(
        "vibemql5.backend_admin.core.subprocess.Popen",
        lambda *_args, **_kwargs: SimpleNamespace(pid=os.getpid()),
    )
    first = admin.start_test_run("unit", "TIP053/UNIT/01")
    second = admin.start_test_run("unit", "TIP053/UNIT/01")
    conflict = admin.start_test_run("py_compile", "TIP053/UNIT/01")
    assert first["state"] == "RUNNING"
    assert second["run_id"] == first["run_id"]
    assert second["idempotent_recovered"] is True
    assert conflict["status"] == "BLOCKED"
    assert conflict["reason_code"] == "TEST_OPERATION_CONFLICT"
