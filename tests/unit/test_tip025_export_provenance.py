from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

import pytest

import vibemql5
from vibemql5.contracts import MCP_TOOL_CATALOG_SHA256, MCP_TOOL_COUNT, MCP_TOOL_NAMES
from vibemql5.core.artifacts import ArtifactManager, BUILD_INPUT_MANIFEST_NAME, BUILD_OUTPUT_MANIFEST_NAME
from vibemql5.core.file_export import FileExportManager

EXPECTED_CATALOG = "a0d2240862369aaf67039b34921bda2b0eeb3aba7e9dae1f4c71c44fd5c40106"


def _root(tmp_path: Path) -> tuple[Path, Path, bytes, bytes]:
    root = tmp_path / "VibeMQL5"
    ws = root / "workspaces" / "BD"
    (ws / "Experts").mkdir(parents=True)
    (ws / "Include").mkdir()
    (ws / "Sets").mkdir()
    source = b"\xef\xbb\xbf#property strict\r\n#include <Tip025.mqh>\r\nvoid OnTick(){}\r\n"
    params = b"InpLots=0.01\r\nInpMode=2\r\n"
    (ws / "Experts" / "EA.mq5").write_bytes(source)
    (ws / "Experts" / "OtherEA.mq5").write_bytes(b"#property strict\r\nvoid OnTick(){}\r\n")
    (ws / "Include" / "Tip025.mqh").write_bytes(b"// include\r\n")
    (ws / "Include" / "UnusedSecret.mqh").write_bytes(b"// unrelated include must not be released\r\n")
    (ws / "Sets" / "Accepted.set").write_bytes(params)
    (root / "runs").mkdir(parents=True)
    (root / "exports").mkdir()
    return root, ws, source, params


def _make_passed_job(root: Path, job_id: str, workspace: str = "BD", ea: str = "Experts/EA.mq5") -> Path:
    run = root / "runs" / job_id
    run.mkdir(parents=True, exist_ok=True)
    (run / "job.json").write_text(json.dumps({
        "job_id": job_id,
        "state": "PASSED",
        "request": {"workspace": workspace, "ea": ea, "set_file": "Sets/Accepted.set"},
    }), encoding="utf-8")
    return run


def test_tip025_identity_keeps_42_tool_catalog_and_schema():
    assert vibemql5.__version__ == "0.2.37"
    assert MCP_TOOL_COUNT == 79
    assert MCP_TOOL_NAMES.count("export_file") == 1
    assert MCP_TOOL_CATALOG_SHA256 == EXPECTED_CATALOG


def test_tip025_snapshot_is_write_once_and_preserves_pre_mutation_bytes(tmp_path: Path):
    root, ws, source_a, set_a = _root(tmp_path)
    artifacts = ArtifactManager(root)
    job_id = "BT-20260910-010101-ABCDEF"
    first = artifacts.capture_build_inputs(job_id, "BD", ws, "Experts/EA.mq5", "Sets/Accepted.set")
    assert first["main_source"]["sha256"] == hashlib.sha256(source_a).hexdigest()
    assert first["parameter_set"]["sha256"] == hashlib.sha256(set_a).hexdigest()

    (ws / "Experts" / "EA.mq5").write_bytes(b"// revision B\n")
    (ws / "Sets" / "Accepted.set").write_bytes(b"InpLots=9\n")
    second = artifacts.capture_build_inputs(job_id, "BD", ws, "Experts/EA.mq5", "Sets/Accepted.set")
    assert second["manifest_sha256"] == first["manifest_sha256"]
    assert (root / "runs" / job_id / "source_snapshot" / "Experts" / "EA.mq5").read_bytes() == source_a
    assert (root / "runs" / job_id / "source_snapshot" / "Sets" / "Accepted.set").read_bytes() == set_a


def test_tip025_snapshot_tamper_fails_closed(tmp_path: Path):
    root, ws, _, _ = _root(tmp_path)
    artifacts = ArtifactManager(root)
    job_id = "BT-20260910-010102-ABCDEF"
    artifacts.capture_build_inputs(job_id, "BD", ws, "Experts/EA.mq5", "Sets/Accepted.set")
    snap = root / "runs" / job_id / "source_snapshot" / "Experts" / "EA.mq5"
    snap.write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="SOURCE_SNAPSHOT_INTEGRITY_MISMATCH"):
        artifacts.snapshot_source(job_id, ws)


def test_tip025_workspace_source_export_is_exact_but_nonhistorical_and_stale_link_fails(tmp_path: Path):
    root, ws, source, params = _root(tmp_path)
    mgr = FileExportManager(root)
    meta = mgr.prepare("workspace_source", "BD", "Experts/EA.mq5")
    assert meta["source_relation"] == "current_workspace_nonhistorical"
    assert meta["sha256"] == hashlib.sha256(source).hexdigest()
    raw, _ = mgr.read_token(meta["uri"].rsplit("/", 1)[1])
    assert raw == source

    pmeta = mgr.prepare("parameter_set", "BD", "Sets/Accepted.set")
    assert pmeta["sha256"] == hashlib.sha256(params).hexdigest()

    (ws / "Experts" / "EA.mq5").write_bytes(b"new revision")
    with pytest.raises(ValueError, match="changed after link creation"):
        mgr.read_token(meta["uri"].rsplit("/", 1)[1])


def test_tip025_job_source_and_selected_set_export_from_immutable_snapshot(tmp_path: Path):
    root, ws, source, params = _root(tmp_path)
    job_id = "BT-20260910-010103-ABCDEF"
    _make_passed_job(root, job_id)
    artifacts = ArtifactManager(root)
    artifacts.capture_build_inputs(job_id, "BD", ws, "Experts/EA.mq5", "Sets/Accepted.set")
    run = root / "runs" / job_id
    (run / "compiled.ex5").write_bytes(b"EX5-A")
    artifacts.write_build_output_manifest(job_id, {"status":"PASSED","errors":0,"warnings":0,"source":"windows_native_metaeditor","expert_name":"EA"})
    (ws / "Experts" / "EA.mq5").write_bytes(b"revision B")
    (ws / "Sets" / "Accepted.set").write_bytes(b"changed=1")

    mgr = FileExportManager(root)
    smeta = mgr.prepare("job_source", job_id, "Experts/EA.mq5")
    assert smeta["source_relation"] == "immutable_job_source_snapshot"
    sraw, _ = mgr.read_token(smeta["uri"].rsplit("/", 1)[1])
    assert sraw == source
    with pytest.raises(ValueError, match="not bound to the job build dependency closure"):
        mgr.prepare("job_source", job_id, "Experts/OtherEA.mq5")
    with pytest.raises(ValueError, match="not bound to the job build dependency closure"):
        mgr.prepare("job_source", job_id, "Include/UnusedSecret.mqh")

    pmeta = mgr.prepare("job_parameter_set", job_id, "Sets/Accepted.set")
    praw, _ = mgr.read_token(pmeta["uri"].rsplit("/", 1)[1])
    assert praw == params
    with pytest.raises(ValueError, match="not the job-bound"):
        mgr.prepare("job_parameter_set", job_id, "Sets/Other.set")


def test_tip025_export_guards_wrong_hash_traversal_absolute_extension_and_symlink(tmp_path: Path):
    root, ws, _, _ = _root(tmp_path)
    mgr = FileExportManager(root)
    with pytest.raises(ValueError, match="precondition mismatch"):
        mgr.prepare("workspace_source", "BD", "Experts/EA.mq5", "0" * 64)
    for bad in ("../EA.mq5", "/tmp/EA.mq5", "C:/EA.mq5"):
        with pytest.raises((ValueError, FileNotFoundError)):
            mgr.prepare("workspace_source", "BD", bad)
    with pytest.raises(ValueError, match="not exportable"):
        mgr.prepare("workspace_source", "BD", "Sets/Accepted.set")

    outside = root / "outside.mq5"
    outside.write_text("// outside", encoding="utf-8")
    link = ws / "Experts" / "link.mq5"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        return
    with pytest.raises(ValueError, match="escapes"):
        mgr.prepare("workspace_source", "BD", "Experts/link.mq5")


def test_tip025_release_bundle_is_deterministic_and_manifest_consistent(tmp_path: Path):
    root, ws, source, params = _root(tmp_path)
    job_id = "BT-20260910-010104-ABCDEF"
    run = _make_passed_job(root, job_id)
    artifacts = ArtifactManager(root)
    inputs = artifacts.capture_build_inputs(job_id, "BD", ws, "Experts/EA.mq5", "Sets/Accepted.set")
    ex5 = b"TIP025-EX5" * 4096
    (run / "compiled.ex5").write_bytes(ex5)
    (run / "compile.log").write_text("Result: 0 errors, 0 warnings\n", encoding="utf-8")
    (run / "compile.json").write_text(json.dumps({"status":"PASSED","errors":0,"warnings":0}), encoding="utf-8")
    (run / "tester.log").write_text("native test evidence\n", encoding="utf-8")
    (run / "result.json").write_text(json.dumps({"status":"PASSED"}), encoding="utf-8")
    artifacts.write_build_output_manifest(job_id, {
        "status": "PASSED", "errors": 0, "warnings": 0,
        "source": "windows_native_metaeditor", "expert_name": "VibeMQL5\\BD\\EA",
    })

    mgr = FileExportManager(root)
    first = mgr.prepare("release_bundle", job_id)
    second = mgr.prepare("release_bundle", job_id)
    assert first["sha256"] == second["sha256"]
    assert first["source_relation"] == "immutable_release_bundle"
    bundle_raw, _ = mgr.read_token(first["uri"].rsplit("/", 1)[1])
    assert hashlib.sha256(bundle_raw).hexdigest() == first["sha256"]

    bundle_path = root / "exports" / "releases" / job_id / f"VibeMQL5-{job_id}-release.zip"
    with zipfile.ZipFile(bundle_path) as zf:
        names = set(zf.namelist())
        assert "Source/Experts/EA.mq5" in names
        assert "Source/Include/Tip025.mqh" in names
        assert "Source/Experts/OtherEA.mq5" not in names
        assert "Source/Include/UnusedSecret.mqh" not in names
        assert "Sets/Accepted.set" in names
        assert "Bin/EA.ex5" in names
        assert "Evidence/build-input-manifest.json" in names
        assert "Evidence/build-output-manifest.json" in names
        assert "MANIFEST.json" in names
        assert "SHA256SUMS.txt" in names
        manifest = json.loads(zf.read("MANIFEST.json"))
        for item in manifest["files"]:
            raw = zf.read(item["path"])
            assert len(raw) == item["bytes"]
            assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        assert manifest["build_input_manifest_sha256"] == inputs["manifest_sha256"]
        assert manifest["source_dependency_count"] == 1
        assert manifest["compiled_ex5_sha256"] == hashlib.sha256(ex5).hexdigest()
        sums = zf.read("SHA256SUMS.txt").decode("utf-8")
        assert hashlib.sha256(zf.read("MANIFEST.json")).hexdigest() in sums


def test_tip025_mutating_workspace_after_bundle_does_not_change_historical_bundle(tmp_path: Path):
    root, ws, _, _ = _root(tmp_path)
    job_id = "BT-20260910-010105-ABCDEF"
    run = _make_passed_job(root, job_id)
    artifacts = ArtifactManager(root)
    artifacts.capture_build_inputs(job_id, "BD", ws, "Experts/EA.mq5", "Sets/Accepted.set")
    (run / "compiled.ex5").write_bytes(b"EX5")
    artifacts.write_build_output_manifest(job_id, {"status":"PASSED","errors":0,"warnings":0,"source":"windows_native_metaeditor","expert_name":"EA"})
    mgr = FileExportManager(root)
    first = mgr.prepare("release_bundle", job_id)
    (ws / "Experts" / "EA.mq5").write_bytes(b"revision C")
    second = mgr.prepare("release_bundle", job_id)
    assert second["sha256"] == first["sha256"]


def test_tip025_immutable_json_exclusive_create_rejects_divergent_race(tmp_path: Path):
    import threading

    root, _, _, _ = _root(tmp_path)
    artifacts = ArtifactManager(root)
    job_id = "COMPILE-20260910-RACE01"
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def writer(value: int) -> None:
        barrier.wait()
        try:
            artifacts.write_json_immutable(job_id, "race.json", {"value": value})
            outcomes.append("PASS")
        except RuntimeError as exc:
            assert "IMMUTABLE_ARTIFACT_CONFLICT" in str(exc)
            outcomes.append("CONFLICT")

    threads = [threading.Thread(target=writer, args=(1,)), threading.Thread(target=writer, args=(2,))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["CONFLICT", "PASS"]
    assert json.loads((root / "runs" / job_id / "race.json").read_text())["value"] in {1, 2}


def test_tip025_completed_job_set_export_is_bound_to_output_manifest(tmp_path: Path):
    root, ws, _, _ = _root(tmp_path)
    job_id = "BT-20260910-010106-ABCDEF"
    run = _make_passed_job(root, job_id)
    artifacts = ArtifactManager(root)
    artifacts.capture_build_inputs(job_id, "BD", ws, "Experts/EA.mq5", "Sets/Accepted.set")
    (run / "compiled.ex5").write_bytes(b"EX5")
    artifacts.write_build_output_manifest(job_id, {"status":"PASSED","errors":0,"warnings":0,"source":"windows_native_metaeditor","expert_name":"EA"})
    # Tamper only the input record after output binding. Snapshot bytes themselves remain untouched.
    inp = run / BUILD_INPUT_MANIFEST_NAME
    data = json.loads(inp.read_text())
    data["workspace"] = "ATTACKER-EDIT"
    inp.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="not bound to the immutable input manifest"):
        FileExportManager(root).prepare("job_parameter_set", job_id, "Sets/Accepted.set")


def test_tip025_existing_release_bundle_tamper_fails_closed(tmp_path: Path):
    root, ws, _, _ = _root(tmp_path)
    job_id = "BT-20260910-010107-ABCDEF"
    run = _make_passed_job(root, job_id)
    artifacts = ArtifactManager(root)
    artifacts.capture_build_inputs(job_id, "BD", ws, "Experts/EA.mq5", "Sets/Accepted.set")
    (run / "compiled.ex5").write_bytes(b"EX5")
    artifacts.write_build_output_manifest(job_id, {"status":"PASSED","errors":0,"warnings":0,"source":"windows_native_metaeditor","expert_name":"EA"})
    mgr = FileExportManager(root)
    meta = mgr.prepare("release_bundle", job_id)
    bundle = root / "exports" / "releases" / job_id / meta["file_name"]
    bundle.write_bytes(b"tampered-not-a-zip")
    with pytest.raises(ValueError, match="integrity validation failed"):
        mgr.prepare("release_bundle", job_id)
