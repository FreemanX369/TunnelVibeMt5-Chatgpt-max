"""Durable synchronous invocation controls using actual storage and MCP dispatch."""
from __future__ import annotations

import asyncio
import inspect
import json
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import UnexpectedToolError

from vibemql5.backend_admin import core
from vibemql5.backend_admin.core import BackendAdmin, BackendAdminError
from vibemql5.backend_admin.tools import register_backend_admin_tools

SECRET = "password=CONTROL_PRIVATE_NEVER_EXPOSE"


def root(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/settings.json").write_text(json.dumps({
        "resource_guard": {}, "retention": {}, "jobs": {},
    }))
    return tmp_path


def index(admin):
    result = admin.read_evidence("backend-admin/test-runs/sync-invocations.json")
    assert result["status"] == "PASS"
    return json.loads(result["content"])


def record(admin, entry):
    return json.loads(admin.read_evidence(entry["evidence_relative_path"])["content"])


@pytest.mark.parametrize("payload", [
    {"status": "PASS", "suite": "unit", "returncode": 0, "stdout_tail": "unchanged", "stderr_tail": ""},
    {"status": "FAIL", "suite": "unit", "returncode": 7, "stdout_tail": "", "stderr_tail": "unchanged"},
    {"status": "STARTED", "suite": "tip033_soak", "recovered": True},
])
def test_normal_return_keeps_object_and_start_facts(tmp_path, monkeypatch, payload):
    admin = BackendAdmin(root(tmp_path))
    starts = []

    def body(suite):
        current = index(admin)
        starts.append(record(admin, current["entries"][-1]))
        assert starts[-1]["state"] == "INVOCATION_STARTED"
        assert starts[-1]["result"] is None
        return payload

    monkeypatch.setattr(admin, "_run_test_suite", body)
    returned = admin.run_tests(payload["suite"])
    assert returned is payload
    current = index(admin)
    entry = current["entries"][-1]
    final = record(admin, entry)
    assert final["state"] == "INVOCATION_RETURNED"
    assert final["result"] == payload
    assert final["invocation_id"] == starts[0]["invocation_id"] == entry["invocation_id"]
    assert final["started_at_utc"] == starts[0]["started_at_utc"] == entry["started_at_utc"]
    assert final["suite"] == starts[0]["suite"] == payload["suite"]
    assert final["descendant_outcome"] == "UNKNOWN"
    assert "worker_pid" not in final and "state" not in entry


@pytest.mark.parametrize("case", ["success", "nonzero", "timeout"])
def test_actual_subprocess_result_and_timeout_are_receipted(tmp_path, monkeypatch, case):
    admin = BackendAdmin(root(tmp_path))
    admin.python = Path(sys.executable)
    requested = []
    originals = []
    child = "import sys; print('CHILD_STDOUT',flush=True); print('CHILD_STDERR',file=sys.stderr,flush=True)"
    child += "; sys.exit(7)" if case == "nonzero" else ""
    child += "; import time; time.sleep(30)" if case == "timeout" else ""

    def bounded_run(argv, timeout):
        requested.append((argv[2], timeout))
        assert record(admin, index(admin)["entries"][-1])["state"] == "INVOCATION_STARTED"
        try:
            return BackendAdmin._run(admin, [sys.executable, "-c", child], timeout=5)
        except subprocess.TimeoutExpired as error:
            originals.append(error)
            raise

    monkeypatch.setattr(admin, "_run", bounded_run)
    out = admin.run_tests("unit")
    assert requested == [("pytest", 300)]
    assert out["status"] == ("PASS" if case == "success" else "FAIL")
    assert "CHILD_STDOUT" in out["stdout_tail"] and "CHILD_STDERR" in out["stderr_tail"]
    final = record(admin, index(admin)["entries"][-1])
    assert final["result"] == out
    if case == "timeout":
        assert len(originals) == 1 and originals[0].timeout == 5
        assert out["reason_code"] == "TEST_RUN_TIMEOUT" and out["returncode"] is None
        assert out["timeout_seconds"] == 5 and out["descendant_outcome"] == "UNKNOWN"
        assert final["state"] == "INVOCATION_TIMEOUT" and final["exception_type"] == "TimeoutExpired"
    else:
        assert out["returncode"] == (0 if case == "success" else 7)
        assert final["state"] == "INVOCATION_RETURNED"


@pytest.mark.parametrize("suite,expected_timeout", [
    ("py_compile", 180), ("unit", 300), ("runtime_forensics", 300),
    ("tip026", 300), ("baseline_aware", 300),
])
def test_original_suite_budgets_and_baseline_denial_remain(tmp_path, monkeypatch, suite, expected_timeout):
    admin = BackendAdmin(root(tmp_path))
    calls = []

    def run(argv, timeout):
        calls.append((argv, timeout))
        return subprocess.CompletedProcess(argv, 5 if suite == "baseline_aware" else 0, "out", "err")

    monkeypatch.setattr(admin, "_run", run)
    out = admin.run_tests(suite)
    assert len(calls) == 1 and calls[0][1] == expected_timeout
    if suite == "baseline_aware":
        assert out["status"] == "FAIL" and out["framework_completed"] is False
        assert out["baseline_conformant"] is False and out["result_class"] == "TEST_RUN_FAILED"
    else:
        assert out == {"status": "PASS", "suite": suite, "returncode": 0,
                       "stdout_tail": "out", "stderr_tail": "err"}


@pytest.mark.parametrize("stdout,stderr", [(b"a" * 9000 + b"OUT", b"b" * 9000 + b"ERR"),
                                           ("a" * 9000 + "OUT", "b" * 9000 + "ERR"),
                                           ("\U0001f642" * 5000, ("\U0001f642" * 5000).encode()),
                                           (None, None)], ids=["bytes", "text", "unicode", "none"])
def test_timeout_tails_bound_bytes_text_and_omit_exception_command(tmp_path, monkeypatch, stdout, stderr):
    admin = BackendAdmin(root(tmp_path))
    original = subprocess.TimeoutExpired([SECRET], 300, output=stdout, stderr=stderr)

    def fail(_suite):
        raise original

    monkeypatch.setattr(admin, "_run_test_suite", fail)
    out = admin.run_tests("unit")
    assert out["status"] == "FAIL" and out["reason_code"] == "TEST_RUN_TIMEOUT"
    for field, value in [("stdout_tail", stdout), ("stderr_tail", stderr)]:
        expected = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""
        assert out[field] == expected[-4096:]
        assert len(out[field]) <= 4096
    final = record(admin, index(admin)["entries"][-1])
    assert SECRET not in json.dumps(final) and SECRET not in json.dumps(out)
    assert final["exception_type"] == "TimeoutExpired"


@pytest.mark.parametrize("timeout", [float("inf"), float("nan"), 2**2000, True, -1, SECRET])
def test_malformed_timeout_metadata_cannot_mask_original_timeout(tmp_path, monkeypatch, timeout):
    admin = BackendAdmin(root(tmp_path))
    original = subprocess.TimeoutExpired([SECRET], timeout)
    monkeypatch.setattr(admin, "_run_test_suite", lambda _suite: (_ for _ in ()).throw(original))
    out = admin.run_tests("unit")
    assert out["status"] == "FAIL" and out["timeout_seconds"] is None
    assert SECRET not in json.dumps(record(admin, index(admin)["entries"][-1]))


def test_unsupported_suite_and_signature_are_unchanged(tmp_path, monkeypatch):
    admin = BackendAdmin(root(tmp_path))
    monkeypatch.setattr(admin, "_run_test_suite", lambda *_a: pytest.fail("Unsupported suite must not execute"))
    assert str(inspect.signature(BackendAdmin.run_tests)) == "(self, suite: 'str') -> 'dict[str, Any]'"
    assert admin.run_tests("unsupported") == {
        "status": "BLOCKED", "reason_code": "TEST_SUITE_NOT_ALLOWED",
        "suite": "unsupported", "allowed_suites": sorted(admin.TEST_SUITES),
    }
    assert not list(admin.test_run_root.iterdir())


def test_recent_cap_keeps_every_record_without_activity_claim(tmp_path, monkeypatch):
    admin = BackendAdmin(root(tmp_path))
    payload = {"status": "PASS", "suite": "unit"}
    monkeypatch.setattr(admin, "_run_test_suite", lambda _suite: payload)
    all_entries = []
    for _ in range(35):
        assert admin.run_tests("unit") is payload
        all_entries.append(index(admin)["entries"][-1])
    current = index(admin)
    assert current["scope"] == "RECENT_DISCOVERY_ONLY" and current["limit"] == 32
    assert current["total_invocations"] == 35 and current["evicted_descriptors"] == 3
    assert current["entries"] == all_entries[-32:]
    assert len({x["invocation_id"] for x in all_entries}) == 35
    for entry in all_entries:
        final = record(admin, entry)
        assert final["started_at_utc"] == entry["started_at_utc"]
        assert final["result"] == payload and final["descendant_outcome"] == "UNKNOWN"


@pytest.mark.parametrize("damage", ["json", "oversized", "not_object", "extra_key", "bool_total", "negative_total",
                                    "bad_counter", "too_many_entries", "bad_id", "unsafe_path", "bad_suite",
                                    "bad_stamp", "invalid_date", "duplicate_id", "directory"])
def test_invalid_index_blocks_body_and_preserves_evidence(tmp_path, monkeypatch, damage):
    admin = BackendAdmin(root(tmp_path))
    monkeypatch.setattr(admin, "_run_test_suite", lambda _s: {"status": "PASS"})
    admin.run_tests("unit")
    original = index(admin)
    path = admin.test_run_root / "sync-invocations.json"
    value = json.loads(json.dumps(original))
    if damage == "json": raw = b"{"
    elif damage == "oversized": raw = b" " * 65_537
    elif damage == "not_object": raw = b"[]"
    elif damage == "directory":
        path.unlink(); path.mkdir(); raw = None
    else:
        if damage == "extra_key": value["extra"] = SECRET
        elif damage == "bool_total": value["total_invocations"] = True
        elif damage == "negative_total": value["total_invocations"] = -1
        elif damage == "bad_counter": value["evicted_descriptors"] = 1
        elif damage == "too_many_entries": value["entries"] *= 33
        elif damage == "bad_id": value["entries"][0]["invocation_id"] = []
        elif damage == "unsafe_path": value["entries"][0]["evidence_relative_path"] = "../../" + SECRET
        elif damage == "bad_suite": value["entries"][0]["suite"] = []
        elif damage == "bad_stamp": value["entries"][0]["started_at_utc"] = SECRET
        elif damage == "invalid_date": value["entries"][0]["started_at_utc"] = "2026-99-07T00:00:00.000+00:00"
        elif damage == "duplicate_id":
            value["entries"] *= 2; value["total_invocations"] = 2
        raw = json.dumps(value).encode()
    if raw is not None: path.write_bytes(raw)
    before = sorted(p.name for p in admin.test_run_root.iterdir())
    monkeypatch.setattr(admin, "_run_test_suite", lambda *_a: pytest.fail("Index fault must block child"))
    with pytest.raises(BackendAdminError, match="^SYNC_TEST_INDEX_"):
        admin.run_tests("unit")
    assert sorted(p.name for p in admin.test_run_root.iterdir()) == before
    if raw is not None: assert path.read_bytes() == raw
    else: assert path.is_dir()
    assert record(admin, original["entries"][0])["state"] == "INVOCATION_RETURNED"


@pytest.mark.parametrize("phase", ["start", "index"])
def test_publication_failure_blocks_body_and_keeps_partial_start(tmp_path, monkeypatch, phase):
    admin = BackendAdmin(root(tmp_path))
    original_write = core.write_json_atomic
    failure = OSError("CONTROL_PUBLICATION_FAILURE")

    def write(path, value):
        if (phase == "start" and path.name.startswith("BTSYNC-")) or (phase == "index" and path.name == "sync-invocations.json"):
            raise failure
        original_write(path, value)

    monkeypatch.setattr(core, "write_json_atomic", write)
    monkeypatch.setattr(admin, "_run_test_suite", lambda *_a: pytest.fail("Publication fault must block child"))
    with pytest.raises(OSError) as caught:
        admin.run_tests("unit")
    assert caught.value is failure
    records = list(admin.test_run_root.glob("BTSYNC-*.json"))
    assert len(records) == (1 if phase == "index" else 0)
    if records: assert json.loads(records[0].read_text())["state"] == "INVOCATION_STARTED"
    assert not (admin.test_run_root / "sync-invocations.json").exists()


@pytest.mark.parametrize("generated", ["../../" + SECRET, "BTSYNC-20261007-000000-ABCDEF12"])
def test_generated_path_invalid_or_collision_never_overwrites(tmp_path, monkeypatch, generated):
    admin = BackendAdmin(root(tmp_path))
    collision = generated.startswith("BTSYNC-")
    path = admin.test_run_root / (generated + ".json") if collision else None
    if path: path.write_text("RETAINED_ORIGINAL_RECORD")
    monkeypatch.setattr(core, "new_id", lambda _prefix: generated)
    monkeypatch.setattr(admin, "_run_test_suite", lambda *_a: pytest.fail("Invalid/colliding id must block child"))
    with pytest.raises(BackendAdminError, match="^SYNC_TEST_INVOCATION_"):
        admin.run_tests("unit")
    if path: assert path.read_text() == "RETAINED_ORIGINAL_RECORD"
    assert not (admin.test_run_root / "sync-invocations.json").exists()


@pytest.mark.parametrize("primary_kind", ["success", "unexpected", "timeout"])
def test_final_write_failure_never_masks_primary_or_returns_pass(tmp_path, monkeypatch, primary_kind):
    admin = BackendAdmin(root(tmp_path))
    publication = OSError("CONTROL_FINAL_PUBLICATION_FAILURE")
    primary = subprocess.TimeoutExpired([SECRET], 300) if primary_kind == "timeout" else ValueError(SECRET)

    def body(_suite):
        if primary_kind == "success": return {"status": "PASS"}
        raise primary

    monkeypatch.setattr(admin, "_run_test_suite", body)
    monkeypatch.setattr(admin, "_finish_sync_test_invocation", lambda *_a, **_k: (_ for _ in ()).throw(publication))
    with pytest.raises(type(publication) if primary_kind == "success" else type(primary)) as caught:
        admin.run_tests("unit")
    assert caught.value is (publication if primary_kind == "success" else primary)
    if primary_kind != "success": assert caught.value.__cause__ is publication
    final = record(admin, index(admin)["entries"][-1])
    assert final["state"] == "INVOCATION_STARTED" and final["result"] is None
    assert final["descendant_outcome"] == "UNKNOWN"


def test_unexpected_error_identity_and_secret_mask_at_actual_sdk(tmp_path, monkeypatch):
    server = MCPServer("sync-receipt-control")
    admin = register_backend_admin_tools(server, root(tmp_path))
    original = ValueError(SECRET)
    monkeypatch.setattr(admin, "_run_test_suite", lambda *_a: (_ for _ in ()).throw(original))
    with pytest.raises(ValueError) as direct:
        admin.run_tests("unit")
    assert direct.value is original
    with pytest.raises(UnexpectedToolError) as dispatched:
        asyncio.run(server.call_tool("backend_run_tests", {"suite": "unit"}, context=SimpleNamespace()))
    assert dispatched.value.__cause__ is original
    assert str(dispatched.value) == "Error executing tool backend_run_tests"
    assert SECRET not in str(dispatched.value)
    current = index(admin)
    assert len(current["entries"]) == 2
    for entry in current["entries"]:
        final = record(admin, entry)
        assert final["state"] == "INVOCATION_EXCEPTION" and final["exception_type"] == "ValueError"
        assert final["result"] is None and SECRET not in json.dumps(final)


def test_actual_sdk_can_discover_held_invocation_and_read_concurrently(tmp_path, monkeypatch):
    server = MCPServer("sync-receipt-control")
    admin = register_backend_admin_tools(server, root(tmp_path))
    entered, release = threading.Event(), threading.Event()
    payload = {"status": "PASS", "suite": "unit", "returncode": 0}

    def body(_suite):
        entered.set()
        assert release.wait(15), "Owned fixture body must be released within its bound"
        return payload

    monkeypatch.setattr(admin, "_run_test_suite", body)

    @server.tool()
    def health_control() -> dict[str, Any]:
        return {"service": "CONTROL_ONLY"}

    async def control():
        pending = asyncio.create_task(server.call_tool("backend_run_tests", {"suite": "unit"}, context=SimpleNamespace()))
        try:
            async def ready():
                while not entered.is_set(): await asyncio.sleep(.005)
            await asyncio.wait_for(ready(), 10)
            health = await server.call_tool("health_control", {}, context=SimpleNamespace())
            discovery = await server.call_tool("backend_read_evidence", {
                "relative_path": "backend-admin/test-runs/sync-invocations.json",
            }, context=SimpleNamespace())
            assert not pending.done() and health.structured_content == {"service": "CONTROL_ONLY"}
            entry = json.loads(discovery.structured_content["content"])["entries"][-1]
            observation = record(admin, entry)
            assert observation["state"] == "INVOCATION_STARTED" and observation["result"] is None
            assert observation["descendant_outcome"] == "UNKNOWN"
        finally:
            release.set()
            result = await asyncio.wait_for(pending, 10)
        assert result.structured_content == payload

    asyncio.run(control())
    assert record(admin, index(admin)["entries"][-1])["state"] == "INVOCATION_RETURNED"


def test_actual_sdk_concurrent_invocations_keep_distinct_records(tmp_path, monkeypatch):
    server = MCPServer("sync-receipt-control")
    admin = register_backend_admin_tools(server, root(tmp_path))
    barrier = threading.Barrier(2)

    def body(suite):
        barrier.wait(timeout=10)
        return {"status": "PASS", "suite": suite}

    monkeypatch.setattr(admin, "_run_test_suite", body)

    async def control():
        return await asyncio.wait_for(asyncio.gather(*[
            server.call_tool("backend_run_tests", {"suite": suite}, context=SimpleNamespace())
            for suite in ["unit", "py_compile"]
        ]), 15)

    results = asyncio.run(control())
    assert [x.structured_content["suite"] for x in results] == ["unit", "py_compile"]
    current = index(admin)
    assert current["total_invocations"] == 2 and current["evicted_descriptors"] == 0
    assert len({entry["invocation_id"] for entry in current["entries"]}) == 2
    for entry in current["entries"]:
        assert record(admin, entry)["result"] == {"status": "PASS", "suite": entry["suite"]}
