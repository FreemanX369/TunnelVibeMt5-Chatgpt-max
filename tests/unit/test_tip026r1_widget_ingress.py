from __future__ import annotations

import hashlib
import inspect
import json
import shutil
import socket
import urllib.error
import sys
import types
from pathlib import Path

import pytest

from vibemql5 import __version__
from vibemql5.contracts import MCP_TOOL_CATALOG_SHA256, MCP_TOOL_COUNT, MCP_TOOL_NAMES
from vibemql5.core.binary_ingress import BinaryIngressManager, _validate_download_url
from vibemql5.core.jobs import JobStore
from vibemql5.worker import run_job

EXPECTED_CATALOG = "a0d2240862369aaf67039b34921bda2b0eeb3aba7e9dae1f4c71c44fd5c40106"


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "VibeMQL5"
    (root / "config" / "presets").mkdir(parents=True)
    (root / "workspaces" / "BD" / "Experts").mkdir(parents=True)
    (root / "workspaces" / "BD" / "Sets").mkdir(parents=True)
    (root / "runs").mkdir(parents=True)
    (root / "logs").mkdir(parents=True)
    data_root = root / "fake-terminal-data"
    (data_root / "MQL5" / "Experts").mkdir(parents=True)
    terminal = root / "fake-terminal" / "terminal64.exe"
    meta = root / "fake-terminal" / "MetaEditor64.exe"
    terminal.parent.mkdir(parents=True)
    terminal.write_bytes(b"")
    meta.write_bytes(b"")
    (root / "config" / "terminals.json").write_text(json.dumps({"terminals": [{
        "alias": "MT5-2", "terminal_path": str(terminal), "metaeditor_path": str(meta),
        "data_hash": "TEST", "data_root": str(data_root), "build": 6182, "enabled": True,
    }]}), encoding="utf-8")
    (root / "config" / "settings.json").write_text(json.dumps({
        "resource_guard": {"disk_warning_gb": 0, "disk_block_gb": 0, "min_free_memory_mb": 0},
        "retention": {"completed_jobs": 20}, "jobs": {"max_concurrent": 1, "compile_timeout_seconds": 120},
        "defaults": {"terminal": "MT5-2"},
        "terminal_policy": {"mode": "fixed", "alias": "MT5-2", "allow_fallback": False,
                            "graceful_close_seconds": 1, "reconnect_timeout_seconds": 1},
    }), encoding="utf-8")
    (root / "config" / "presets" / "smoke.json").write_text(json.dumps({
        "symbol": "XAUUSDm", "period": "M1", "model": 4, "deposit": 10000,
        "currency": "USD", "leverage": 1000, "visual": False,
    }), encoding="utf-8")
    return root


def _fake_download(manager: BinaryIngressManager, payload: bytes, file_name: str, file_id: str):
    def impl(descriptor):
        assert descriptor["file_id"] == file_id
        assert descriptor["file_name"] == file_name
        # The downloader is already tested by TIP-026. This unit isolates R1 source/provenance
        # semantics while still requiring a disposable file owned by BinaryIngressManager.
        target = manager.tmp / "authorized-widget-download.ex5.tmp"
        target.write_bytes(payload)
        return target, {
            "file_id": file_id,
            "file_name": file_name,
            "mime_type": descriptor.get("mime_type") or "application/octet-stream",
            "bytes": len(payload),
        }
    return impl


def test_tip026r1_identity_and_ordered_catalog():
    assert __version__ == "0.2.39"
    assert MCP_TOOL_COUNT == 79
    assert MCP_TOOL_CATALOG_SHA256 == EXPECTED_CATALOG
    start = MCP_TOOL_NAMES.index("import_ex5")
    assert MCP_TOOL_NAMES[start:start + 5] == (
        "import_ex5", "open_ex5_ingress", "import_ex5_authorized_file", "get_ex5_import_receipt", "launch_test"
    )
    assert len(set(MCP_TOOL_NAMES)) == 79


def test_tip026r1_widget_authorized_import_reuses_same_immutable_ref_and_records_truthful_source(tmp_path: Path, monkeypatch):
    root = _root(tmp_path)
    payload = b"WSLOW-EX5-WIDGET" * 4096
    sha = hashlib.sha256(payload).hexdigest()
    source = tmp_path / "WSLOW public v1.12.ex5"
    source.write_bytes(payload)
    manager = BinaryIngressManager(root)

    # Existing TIP-026 local/native path establishes the immutable ref first.
    native = manager.import_local_file(
        "BD", source, "Experts/WSLOW public v1.12.ex5", sha,
        source="WINDOWS_NATIVE_QUALIFICATION_FILE",
    )
    secret_url = "https://files.oaiusercontent.com/private/temporary?sig=DO_NOT_PERSIST"
    monkeypatch.setattr(manager, "_download_file_param", _fake_download(
        manager, payload, "WSLOW public v1.12.ex5", "file_widget_123"
    ))
    widget = manager.import_authorized_file(
        "BD",
        file_id="file_widget_123",
        download_url=secret_url,
        file_name="WSLOW public v1.12.ex5",
        mime_type="application/octet-stream",
        destination_path="Experts/WSLOW public v1.12.ex5",
        expected_sha256=sha,
        overwrite=False,
    )

    assert widget["status"] == "ALREADY_PRESENT"
    assert widget["ea_binary_ref"] == native["ea_binary_ref"]
    assert widget["sha256"] == sha
    assert widget["bytes"] == len(payload)
    assert manager.resolve_for_launch("BD", "Experts/WSLOW public v1.12.ex5", widget["ea_binary_ref"])["sha256"] == sha

    provenance = manager.import_provenance(widget["ea_binary_ref"])
    assert provenance["source"] == "CHATGPT_WIDGET_FILE_IMPORT"
    assert provenance["source_file_id"] == "file_widget_123"
    assert "CHATGPT_WIDGET_FILE_IMPORT" in provenance["sources"]
    assert "WINDOWS_NATIVE_QUALIFICATION_FILE" in provenance["sources"]

    receipt_text = "\n".join(p.read_text(encoding="utf-8") for p in manager.imports.glob("IMPORT-*.json"))
    assert "DO_NOT_PERSIST" not in receipt_text
    assert secret_url not in receipt_text


def test_tip026r1_widget_authorized_import_calls_shared_downloader_and_failclosed_hash(tmp_path: Path, monkeypatch):
    root = _root(tmp_path)
    payload = b"EX5-WIDGET" * 128
    manager = BinaryIngressManager(root)
    monkeypatch.setattr(manager, "_download_file_param", _fake_download(manager, payload, "a.ex5", "file_a"))
    with pytest.raises(ValueError, match="EXPECTED_SHA256_MISMATCH"):
        manager.import_authorized_file(
            "BD", file_id="file_a", download_url="https://files.oaiusercontent.com/x",
            file_name="a.ex5", destination_path="Experts/a.ex5", expected_sha256="0" * 64,
        )
    assert not list(manager.bindings.glob("*.json"))
    assert not list(manager.objects.rglob("*.ex5"))


def test_tip026r1_authorized_url_still_rejects_private_resolution(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(ValueError, match="IMPORT_DOWNLOAD_HOST_UNSAFE"):
        _validate_download_url("https://files.oaiusercontent.com/private")


def _install_fake_mcp(monkeypatch):
    class FakeContext:
        pass

    class FakeModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeMCPServer:
        def __init__(self, name, **kwargs):
            self.name = name
            self.kwargs = kwargs
            self.tools = {}
            self.tool_meta = {}
            self.resources = {}
        def tool(self, **kwargs):
            def deco(fn):
                inspect.signature(fn, eval_str=True)
                self.tools[fn.__name__] = fn
                self.tool_meta[fn.__name__] = kwargs
                return fn
            return deco
        def resource(self, uri, **kwargs):
            def deco(fn):
                self.resources[uri] = (fn, kwargs)
                return fn
            return deco

    server_mod = types.ModuleType("mcp.server.mcpserver")
    server_mod.MCPServer = FakeMCPServer
    server_mod.Context = FakeContext
    types_mod = types.ModuleType("mcp.types")
    for name in ("CallToolResult", "ResourceLink", "TextContent", "ToolAnnotations"):
        setattr(types_mod, name, FakeModel)
    monkeypatch.setitem(sys.modules, "mcp", types.ModuleType("mcp"))
    monkeypatch.setitem(sys.modules, "mcp.server", types.ModuleType("mcp.server"))
    monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", server_mod)
    monkeypatch.setitem(sys.modules, "mcp.types", types_mod)
    return FakeMCPServer


def test_tip037_continuity_tool_annotations_match_side_effects(monkeypatch, tmp_path: Path):
    _install_fake_mcp(monkeypatch)
    from vibemql5.adapters import mcp as adapter

    server = adapter.create_server(_root(tmp_path), transport="stdio")
    for name in ("server_info", "health", "get_continuity", "read_continuity_events", "verify_continuity"):
        annotations = server.tool_meta[name]["annotations"]
        assert annotations.read_only_hint is True
        assert annotations.destructive_hint is False
        assert annotations.open_world_hint is False

    append = server.tool_meta["append_continuity_event"]["annotations"]
    assert append.read_only_hint is False
    assert append.destructive_hint is True
    assert append.idempotent_hint is True
    assert append.open_world_hint is False


def test_tip026r1_mcp_surface_widget_resource_visibility_and_direct_fileparam_backward_compat(monkeypatch, tmp_path: Path):
    _install_fake_mcp(monkeypatch)
    from vibemql5.adapters import mcp as adapter
    root = _root(tmp_path)
    server = adapter.create_server(root, transport="stdio")

    assert len(server.tools) == 79
    assert set(server.tools) == set(MCP_TOOL_NAMES)
    assert server.tool_meta["import_ex5"]["meta"] == {"openai/fileParams": ["file"]}

    render_meta = server.tool_meta["open_ex5_ingress"]["meta"]
    assert render_meta["ui"]["resourceUri"] == "ui://vibemql5/ex5-ingress-r1.html"
    assert render_meta["ui"]["visibility"] == ["model", "app"]
    assert render_meta["openai/outputTemplate"] == "ui://vibemql5/ex5-ingress-r1.html"
    assert render_meta["openai/widgetAccessible"] is True

    backend_meta = server.tool_meta["import_ex5_authorized_file"]["meta"]
    assert backend_meta["ui"]["visibility"] == ["app"]
    assert backend_meta["openai/widgetAccessible"] is True
    assert "download_url" in inspect.signature(server.tools["import_ex5_authorized_file"]).parameters
    assert "ea_binary_ref" in inspect.signature(server.tools["launch_test"]).parameters

    uri = "ui://vibemql5/ex5-ingress-r1.html"
    assert uri in server.resources
    resource_fn, resource_meta = server.resources[uri]
    assert resource_meta["mime_type"] == "text/html;profile=mcp-app"
    html = resource_fn()
    assert "window.openai" in html
    assert "host.uploadFile" in html
    assert "host.selectFiles" in html
    assert "host.getFileDownloadUrl" in html
    assert 'host.callTool("import_ex5_authorized_file"' in html

    info = server.tools["server_info"]()
    assert info["tool_count"] == 79
    assert info["tool_visibility"] == {
        "server_catalog_count": 79,
        "model_visible_expected_count": 78,
        "app_only_tools": ["import_ex5_authorized_file"],
    }
    assert info["generic_shell_exposed"] is True
    assert info["binary_ingress_transport"] == "openai/fileParams"
    assert info["binary_ingress_transports"] == ["openai/fileParams", "chatgpt/widget-authorized-url"]
    assert info["binary_ingress_widget_schema"] == "1.0"
    assert info["binary_ingress_widget_import_tool"] == "import_ex5_authorized_file"


def test_tip026r1_widget_static_security_and_no_url_persistence_surface():
    from vibemql5.adapters.ex5_widget import EX5_INGRESS_WIDGET_HTML
    html = EX5_INGRESS_WIDGET_HTML
    assert "fetch(" not in html
    assert "XMLHttpRequest" not in html
    assert "localStorage" not in html
    assert "sessionStorage" not in html
    assert "console." not in html
    assert "btoa(" not in html
    assert "FileReader" not in html
    assert "download_url: downloadUrl" in html
    assert "privateContent:{ea_binary_ref:ref,import_id:data.import_id,sha256:data.sha256,bytes:data.bytes,workspace:data.workspace,path:data.path}" in html
    assert "downloadUrl" not in html.split("privateContent:", 1)[1].split("}}", 1)[0]


def test_tip026r1_facade_delegates_authorized_import_under_mutation_lock(tmp_path: Path, monkeypatch):
    from vibemql5.core.facade import ToolFacade
    root = _root(tmp_path)
    facade = ToolFacade(root)
    seen = {}
    def fake_import(workspace, **kwargs):
        seen["workspace"] = workspace
        seen.update(kwargs)
        return {"status": "IMPORTED", "ea_binary_ref": "BIN-" + "1" * 64}
    monkeypatch.setattr(facade.binary_ingress, "import_authorized_file", fake_import)
    out = facade.import_ex5_authorized_file(
        "BD", "file_x", "https://files.oaiusercontent.com/x", "x.ex5",
        "application/octet-stream", "Experts/x.ex5", "a" * 64, False,
    )
    assert out["status"] == "IMPORTED"
    mutation_operation_id = seen.pop("mutation_operation_id")
    assert mutation_operation_id.startswith("MUT-") and len(mutation_operation_id) == 20
    assert seen == {
        "workspace": "BD", "file_id": "file_x", "download_url": "https://files.oaiusercontent.com/x",
        "file_name": "x.ex5", "mime_type": "application/octet-stream", "destination_path": "Experts/x.ex5",
        "expected_sha256": "a" * 64, "overwrite": False,
    }


def test_tip026r1_expired_or_unavailable_authorized_url_fails_before_binding(tmp_path: Path, monkeypatch):
    root = _root(tmp_path)
    manager = BinaryIngressManager(root)
    def expired(_descriptor):
        raise urllib.error.HTTPError("https://files.oaiusercontent.com/expired", 403, "expired", {}, None)
    monkeypatch.setattr(manager, "_download_file_param", expired)
    with pytest.raises(urllib.error.HTTPError):
        manager.import_authorized_file(
            "BD", file_id="file_expired", download_url="https://files.oaiusercontent.com/expired",
            file_name="expired.ex5", destination_path="Experts/expired.ex5",
        )
    assert not list(manager.bindings.glob("*.json"))
    assert not list(manager.objects.rglob("*.ex5"))
    assert not list(manager.imports.glob("IMPORT-*.json"))


def test_tip026r1_widget_same_path_different_bytes_conflicts_without_overwrite(tmp_path: Path, monkeypatch):
    root = _root(tmp_path)
    manager = BinaryIngressManager(root)
    payload_a = b"A" * 2048
    payload_b = b"B" * 2048
    monkeypatch.setattr(manager, "_download_file_param", _fake_download(manager, payload_a, "same.ex5", "file_a"))
    first = manager.import_authorized_file(
        "BD", file_id="file_a", download_url="https://files.oaiusercontent.com/a", file_name="same.ex5",
        destination_path="Experts/same.ex5", expected_sha256=hashlib.sha256(payload_a).hexdigest(),
    )
    monkeypatch.setattr(manager, "_download_file_param", _fake_download(manager, payload_b, "same.ex5", "file_b"))
    with pytest.raises(ValueError, match="DESTINATION_CONFLICT"):
        manager.import_authorized_file(
            "BD", file_id="file_b", download_url="https://files.oaiusercontent.com/b", file_name="same.ex5",
            destination_path="Experts/same.ex5", expected_sha256=hashlib.sha256(payload_b).hexdigest(), overwrite=False,
        )
    assert manager.resolve_for_launch("BD", "Experts/same.ex5", first["ea_binary_ref"])["sha256"] == hashlib.sha256(payload_a).hexdigest()


def test_tip026r1_widget_ref_runs_mock_without_compile_and_job_manifest_keeps_widget_source(tmp_path: Path, monkeypatch):
    root = _root(tmp_path)
    payload = b"WIDGET-IMPORTED-EX5" * 256
    sha = hashlib.sha256(payload).hexdigest()
    manager = BinaryIngressManager(root)
    monkeypatch.setattr(manager, "_download_file_param", _fake_download(manager, payload, "widget.ex5", "file_widget_job"))
    imported = manager.import_authorized_file(
        "BD", file_id="file_widget_job", download_url="https://files.oaiusercontent.com/job",
        file_name="widget.ex5", destination_path="Experts/widget.ex5", expected_sha256=sha,
    )
    request = {
        "workspace": "BD", "ea": "Experts/widget.ex5", "ea_binary_ref": imported["ea_binary_ref"],
        "terminal": "MT5-2", "preset": "smoke", "set_file": None,
        "overrides": {"from_date": "2026.08.26", "to_date": "2026.08.27"},
        "mock": True, "test_timeout": 0,
    }
    job = JobStore(root).create(request)
    run_job(root, job["job_id"])
    result = json.loads((root / "runs" / job["job_id"] / "result.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "runs" / job["job_id"] / "build-input-manifest.json").read_text(encoding="utf-8"))
    assert result["status"] == "PASSED"
    assert result["compile"]["status"] == "NOT_REQUIRED"
    assert result["compile"]["source"] == "imported_ex5"
    assert result["build_input"]["sha256"] == sha
    assert (root / "runs" / job["job_id"] / "compiled.ex5").read_bytes() == payload
    assert manifest["imported_ex5"]["source"] == "CHATGPT_WIDGET_FILE_IMPORT"
    assert manifest["imported_ex5"]["ingress_provenance"]["source_file_id"] == "file_widget_job"
