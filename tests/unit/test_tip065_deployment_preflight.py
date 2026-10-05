"""Read-only deployment observations; fixtures never initialize a real installation."""
from __future__ import annotations

import builtins
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from ownership_fixture import install_closed
from vibemql5.core import deployment_preflight as module
from vibemql5.core.native_ownership import OwnershipAuthority, OwnershipBlocked

SECRET = "PRIVATE_FIXTURE_VALUE_DO_NOT_EXPOSE"


def files(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def no_effects(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("observation attempted a mutation, lock, network or process")
    for name in ("mkdir", "write_text", "write_bytes", "touch", "unlink", "rename", "replace"):
        monkeypatch.setattr(Path, name, forbidden)
    monkeypatch.setattr(OwnershipAuthority, "transaction", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    original_open = os.open
    def read_only(path, flags, *args, **kwargs):
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        return original_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", read_only)
    original_import = builtins.__import__
    def without_packages(name, *args, **kwargs):
        assert not name.startswith(("cryptography", "mcp", "MetaTrader5", "vibemql5.fleet.native", "vibemql5.fleet.sdk"))
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", without_packages)


def assert_observation_only(result):
    assert result["activation"] == "NOT_QUALIFIED"
    assert result["physical_qualification"] == "NOT_RUN"
    assert result["ownership"]["consistency"] == "TWO_PASSES_NON_ATOMIC_NO_LOCK"
    assert result["source_identity"]["evidence_scope"] == "CURRENT_ON_DISK_NOT_LOADED_CODE_IDENTITY"
    encoded = json.dumps(result)
    assert SECRET not in encoded
    assert '"admission"' not in encoded and '"ready"' not in encoded


def test_absent_root_observed_without_creating_anything_or_loading_packages(tmp_path, monkeypatch):
    root = tmp_path / "absent"
    before = set(sys.modules)
    no_effects(monkeypatch)
    result = module.deployment_preflight(root)
    assert result["ownership"]["reason_code"] == "INSTALL_MISSING"
    assert result["ownership"]["observation"] == "OBSERVED"
    assert not root.exists()
    assert not any(name.startswith(("mcp", "cryptography", "MetaTrader5")) for name in set(sys.modules) - before)
    assert_observation_only(result)


@pytest.mark.parametrize("fault,expected", [
    ("closed", "OBSERVED_CLOSED"), ("active", "ACTIVE_RECOVERY_REQUIRED"),
    ("marker_missing", "INSTALL_MISSING"), ("state_missing", "AUTHORITY_MISSING"),
    ("migrating", "INSTALL_MIGRATING"), ("marker_corrupt", "INSTALL_INVALID"),
    ("state_corrupt", "AUTHORITY_INVALID"), ("marker_array", "INSTALL_INVALID"),
    ("state_array", "AUTHORITY_INVALID"), ("epoch", "EPOCH_MISMATCH"),
    ("generation", "AUTHORITY_INVALID"),
])
def test_actual_record_faults_share_validation_without_mutating_authority(tmp_path, monkeypatch, fault, expected):
    authority = install_closed(tmp_path)
    marker = json.loads(authority.marker_path.read_text())
    state = json.loads(authority.path.read_text())
    marker["private_fixture"] = SECRET
    state["private_fixture"] = SECRET
    if fault == "migrating": marker["disposition"] = "MIGRATING"
    if fault == "epoch": state["epoch"] = "different-" + SECRET
    if fault == "generation": state["generation"] = 0
    if fault == "active":
        state.update(disposition="ACTIVE", phase="CREATE_ATTEMPT", descendants="UNKNOWN",
                     token=SECRET, operation_id=SECRET, kind=SECRET,
                     parent={"pid": 1, "creation": "1", "image": str(tmp_path / SECRET)})
    authority.marker_path.write_text(json.dumps(marker))
    authority.path.write_text(json.dumps(state))
    if fault == "marker_missing": authority.marker_path.unlink()
    if fault == "state_missing": authority.path.unlink()
    if fault == "marker_corrupt": authority.marker_path.write_text('{"' + SECRET)
    if fault == "state_corrupt": authority.path.write_text('{"' + SECRET)
    if fault == "marker_array": authority.marker_path.write_text('[]')
    if fault == "state_array": authority.path.write_text('[]')
    before = files(tmp_path)
    if fault not in {"closed", "active"}:
        with pytest.raises(OwnershipBlocked) as error: authority.load()
        assert error.value.reason == expected
    no_effects(monkeypatch)
    result = module.deployment_preflight(tmp_path)
    assert result["ownership"]["reason_code"] == expected
    assert result["ownership"]["observation"] == "OBSERVED"
    if fault == "closed": assert result["ownership"]["disposition"] == "CLOSED"
    if fault == "active": assert result["ownership"]["phase"] == "CREATE_ATTEMPT"
    assert files(tmp_path) == before
    assert_observation_only(result)


def test_scoped_presence_fences_without_opening_or_reading_its_contents(tmp_path, monkeypatch):
    install_closed(tmp_path)
    path = tmp_path / "state/fleet/scoped-install.json"
    path.parent.mkdir(); path.write_bytes(SECRET.encode() * (module.RECORD_LIMIT + 1))
    original_open = os.open
    def no_scoped_open(selected, *args, **kwargs):
        assert Path(selected) != path
        return original_open(selected, *args, **kwargs)
    monkeypatch.setattr(os, "open", no_scoped_open)
    no_effects(monkeypatch)
    result = module.deployment_preflight(tmp_path)
    assert result["ownership"]["reason_code"] == "SCOPED_OWNERSHIP_REQUIRED"
    assert result["ownership"]["files"]["scoped_installation"] == {"status": "PRESENT"}
    assert_observation_only(result)


@pytest.mark.parametrize("fault", ["oversized", "denied", "directory"])
def test_incomplete_observation_never_converts_fault_into_closed_or_absent(tmp_path, monkeypatch, fault):
    authority = install_closed(tmp_path)
    if fault == "oversized": authority.path.write_bytes(SECRET.encode() * module.RECORD_LIMIT)
    if fault == "directory": authority.path.unlink(); authority.path.mkdir()
    if fault == "denied":
        original_open = os.open
        def denied(path, *args, **kwargs):
            if Path(path) == authority.path: raise PermissionError(SECRET)
            return original_open(path, *args, **kwargs)
        monkeypatch.setattr(os, "open", denied)
    no_effects(monkeypatch)
    result = module.deployment_preflight(tmp_path)
    assert result["ownership"]["observation"] == "INCOMPLETE"
    assert result["ownership"]["reason_code"] == "SNAPSHOT_UNAVAILABLE"
    assert "disposition" not in result["ownership"]
    assert_observation_only(result)


def test_changed_authority_between_passes_has_no_closed_generation_claim(tmp_path, monkeypatch):
    authority = install_closed(tmp_path)
    state = json.loads(authority.path.read_text())
    original_snapshot = module._snapshot
    calls = []
    def replacing(path, limit):
        if path == authority.path:
            calls.append(path)
            if len(calls) == 2: authority.path.write_text(json.dumps({**state, "generation": 2}))
        return original_snapshot(path, limit)
    monkeypatch.setattr(module, "_snapshot", replacing)
    result = module.deployment_preflight(tmp_path)
    assert len(calls) == 2
    assert result["ownership"]["observation"] == "CONCURRENT"
    assert result["ownership"]["reason_code"] == "SNAPSHOT_CHANGED"
    assert "generation" not in result["ownership"]
    assert_observation_only(result)


@pytest.mark.parametrize("limit", [module.RECORD_LIMIT, module.SOURCE_LIMIT])
def test_oversized_snapshot_reads_only_cap_plus_one(tmp_path, monkeypatch, limit):
    path = tmp_path / "large.json"
    path.write_bytes(b"x" * (limit + 1000))
    original_fdopen = os.fdopen
    sizes = []
    class Traced:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): return self
        def __exit__(self, *args): self.stream.close()
        def fileno(self): return self.stream.fileno()
        def read(self, size):
            sizes.append(size)
            assert size == limit + 1
            return self.stream.read(size)
    monkeypatch.setattr(os, "fdopen", lambda *args, **kwargs: Traced(original_fdopen(*args, **kwargs)))
    assert module._snapshot(path, limit)["status"] == "TOO_LARGE"
    assert sizes == [limit + 1]


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink control; actual Windows reparse qualification is separate")
def test_symlink_ancestor_is_not_followed_to_another_record(tmp_path, monkeypatch):
    actual = tmp_path / "actual"; actual.mkdir(); install_closed(actual)
    root = tmp_path / "link"; root.symlink_to(actual, target_is_directory=True)
    original_open = os.open
    def no_authority_read(path, *args, **kwargs):
        assert "native-ownership" not in str(path)
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(os, "open", no_authority_read)
    no_effects(monkeypatch)
    result = module.deployment_preflight(root)
    assert result["ownership"]["observation"] == "INCOMPLETE"
    assert_observation_only(result)


@pytest.mark.skipif(os.name == "nt", reason="POSIX nonblocking FIFO swap control; no Windows FIFO primitive")
def test_regular_file_swapped_to_fifo_before_open_is_nonblocking_and_incomplete(tmp_path, monkeypatch):
    authority = install_closed(tmp_path)
    original_open = os.open
    attempts = []
    def swap(path, flags, *args, **kwargs):
        if Path(path) == authority.path and not attempts:
            attempts.append(path)
            authority.path.unlink(); os.mkfifo(authority.path)
            assert flags & os.O_NONBLOCK
        return original_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", swap)
    result = module.deployment_preflight(tmp_path)
    assert len(attempts) == 1
    assert result["ownership"]["observation"] == "CONCURRENT"
    assert "disposition" not in result["ownership"]
    assert_observation_only(result)


@pytest.mark.skipif(os.name != "nt", reason="Actual Win32 retained file identity requires Windows; no SDK/MT5")
def test_windows_retained_identity_positive_and_fresh_path_match(tmp_path):
    authority = install_closed(tmp_path)
    with authority.path.open("rb") as retained:
        with authority.path.open("rb") as same:
            assert module._handle_facts(retained.fileno()) == module._handle_facts(same.fileno())
        other = tmp_path / "same-bytes-other-file.json"
        other.write_bytes(authority.path.read_bytes())
        with other.open("rb") as different:
            assert module._handle_facts(retained.fileno()) != module._handle_facts(different.fileno())
    result = module.deployment_preflight(tmp_path)
    assert result["ownership"]["reason_code"] == "OBSERVED_CLOSED"
    assert result["ownership"]["observation"] == "OBSERVED"
    assert result["source_identity"]["observation"] == "OBSERVED"
    assert_observation_only(result)


@pytest.mark.skipif(os.name != "nt", reason="Actual Win32 fresh-path replacement identity control requires Windows; no SDK/MT5")
def test_windows_retained_handle_rejects_fresh_path_replacement(tmp_path, monkeypatch):
    authority = install_closed(tmp_path)
    other = tmp_path / "replacement.json"
    other.write_bytes(authority.path.read_bytes())
    original_open = os.open
    attempts = []
    def different_path(path, flags, *args, **kwargs):
        if Path(path) == authority.path:
            attempts.append(path)
            if len(attempts) == 2:
                return original_open(other, flags, *args, **kwargs)
        return original_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", different_path)
    result = module.deployment_preflight(tmp_path)
    assert result["ownership"]["observation"] == "CONCURRENT"
    assert "disposition" not in result["ownership"]
    assert_observation_only(result)


@pytest.mark.parametrize("version,expected", [
    ("50.0.1", "IN_RANGE"), ("50.0", "IN_RANGE"), ("49.99.99", "OUT_OF_RANGE"),
    ("51.0", "OUT_OF_RANGE"), ("50.0rc1", "UNKNOWN"), ("50.0+local", "UNKNOWN"),
    (SECRET, "UNKNOWN"), ("5" * 129, "UNKNOWN"), (None, "UNKNOWN"),
])
def test_crypto_metadata_range_and_unevaluated_formats_have_no_qualification(tmp_path, monkeypatch, version, expected):
    monkeypatch.setattr(module.metadata, "version", lambda name: version if name == "cryptography" else "2.1.1")
    result = module.deployment_preflight(tmp_path)
    crypto = result["runtime_metadata"]["cryptography"]
    assert crypto["constraint_observation"] == expected
    if expected == "UNKNOWN": assert crypto["version"] is None
    assert crypto["evidence_scope"] == "DISTRIBUTION_METADATA_ONLY"
    assert_observation_only(result)


@pytest.mark.parametrize("version,expected", [("2.1.1", "IN_RANGE"), ("2.0.99", "OUT_OF_RANGE"), ("3.0.0", "OUT_OF_RANGE")])
def test_mcp_metadata_expected_constraint_without_importing_package(tmp_path, monkeypatch, version, expected):
    monkeypatch.setattr(module.metadata, "version", lambda name: version if name == "mcp" else "50.0.1")
    no_effects(monkeypatch)
    result = module.deployment_preflight(tmp_path)
    assert result["runtime_metadata"]["mcp"]["constraint_observation"] == expected
    assert_observation_only(result)


@pytest.mark.parametrize("missing", [True, False])
def test_metadata_missing_or_failed_is_sanitized_unknown(tmp_path, monkeypatch, missing):
    def unavailable(name):
        raise module.metadata.PackageNotFoundError(SECRET) if missing else OSError(SECRET)
    monkeypatch.setattr(module.metadata, "version", unavailable)
    result = module.deployment_preflight(tmp_path)
    for name in ("cryptography", "mcp"):
        row = result["runtime_metadata"][name]
        assert row["version"] is None and row["constraint_observation"] == "UNKNOWN"
        assert row["reason_code"] == ("METADATA_MISSING" if missing else "METADATA_READ_FAILED")
    assert_observation_only(result)


@pytest.mark.parametrize("version,expected", [((3, 11, 9), "OUT_OF_RANGE"), ((3, 12, 0), "IN_RANGE"), ((3, 13, 0), "OUT_OF_RANGE")])
def test_python_constraint_reports_interpreter_version_only(tmp_path, monkeypatch, version, expected):
    monkeypatch.setattr(module.sys, "version_info", version)
    monkeypatch.setattr(module.metadata, "version", lambda name: "2.1.1" if name == "mcp" else "50.0.1")
    result = module.deployment_preflight(tmp_path)
    assert result["runtime_metadata"]["python"]["constraint_observation"] == expected
    assert_observation_only(result)


def test_cli_preflight_bypasses_facade_and_configuration(tmp_path, monkeypatch, capsys):
    from vibemql5.adapters import cli
    from vibemql5 import config
    def forbidden(*args, **kwargs): pytest.fail("preflight constructed a facade or read configuration")
    monkeypatch.setattr(cli, "ToolFacade", forbidden)
    monkeypatch.setattr(config, "load_json", forbidden)
    root = tmp_path / "missing"
    no_effects(monkeypatch)
    assert cli.main(["--root", str(root), "deployment-preflight"]) is None
    result = json.loads(capsys.readouterr().out)
    assert result["ownership"]["reason_code"] == "INSTALL_MISSING"
    assert not root.exists()
    assert_observation_only(result)


def test_existing_mcp_catalog_and_all_input_schemas_preserved_with_additive_info(tmp_path, monkeypatch):
    from test_tip055a_runtime_forensics_identity import make_terminal, write_config
    from vibemql5.adapters import mcp
    from vibemql5.contracts import MCP_TOOL_NAMES, MCP_TOOL_CATALOG_SHA256
    write_config(tmp_path, [make_terminal(tmp_path)])
    (tmp_path / "config/settings.json").write_text(json.dumps({"resource_guard": {}, "retention": {}, "jobs": {},
        "terminal_policy": {"mode": "fixed", "alias": "MT5-2"}}))
    monkeypatch.setattr(mcp.ToolFacade, "reconcile_cancelled_jobs", lambda *args, **kwargs: {})
    server = mcp.create_server(tmp_path)
    tools = server._tool_manager._tools
    assert tuple(tools) == MCP_TOOL_NAMES and len(tools) == 85
    assert hashlib.sha256(("\n".join(tools) + "\n").encode()).hexdigest() == MCP_TOOL_CATALOG_SHA256
    schemas = {name: tool.parameters for name, tool in tools.items()}
    assert hashlib.sha256(json.dumps(schemas, sort_keys=True, separators=(",", ":")).encode()).hexdigest() == "64337437115a20a8555cc1214706a503b985195dbdbd219de2adfa35e2c8134d"
    result = tools["server_info"].fn()
    assert result["tool_count"] == 85
    assert_observation_only(result["deployment_preflight"])
