import base64
import copy

import pytest

from vibemql5.fleet.artifact_proxy import ArtifactProxy, validate_chunk, validate_complete
from vibemql5.fleet.job_journal import JournalError

DEVICE = "dev_" + "a" * 32
TARGET = {"schema": "fleet.target/1", "device_id": DEVICE, "terminal_id": "term_" + "b" * 32,
          "route_generation": 1, "terminal_generation": 1}
JOB = "BT-20261003-010000-ABC123"
ART = "art_" + "c" * 32


def registered(tmp_path):
    proxy = ArtifactProxy(tmp_path, node_id=DEVICE, installation_id="install-a", max_artifact_bytes=100, max_chunk_bytes=4)
    directory = tmp_path / "runs" / JOB; directory.mkdir(parents=True)
    path = directory / "evidence.bin"; path.write_bytes(b"12345678")
    scope = dict(artifact_id=ART, global_job_id="fjob_" + "d" * 32, local_job_id=JOB, frozen_target=TARGET)
    manifest = proxy.register(**scope, relative_path="evidence.bin")
    return proxy, scope, manifest, path


def test_immutable_scoped_chunks_and_total_receipt_without_restoration(tmp_path, monkeypatch):
    proxy, scope, manifest, _ = registered(tmp_path)
    monkeypatch.setattr("vibemql5.core.jobs.JobManager.get_job", lambda *_: pytest.fail("read must not restore"))
    chunks = [proxy.chunk(**scope, expected_sha256=manifest["sha256"], offset=n, length=4) for n in (0, 4)]
    raw = b"".join(validate_chunk(chunk, manifest=manifest, offset=n, length=4) for chunk, n in zip(chunks, (0, 4)))
    assert validate_complete(raw, manifest) == b"12345678"
    assert "relative_path" not in manifest and "url" not in manifest


@pytest.mark.parametrize("field,value", [("global_job_id", "other-job"), ("local_job_id", "BT-20261003-010000-DEF456"),
    ("frozen_target", {**TARGET, "device_id": "dev_" + "f" * 32}), ("expected_sha256", "0" * 64)])
def test_wrong_node_job_target_or_hash_denied(tmp_path, field, value):
    proxy, scope, manifest, _ = registered(tmp_path)
    values = {**scope, "expected_sha256": manifest["sha256"], "offset": 0, "length": 4, field: value}
    with pytest.raises(JournalError): proxy.chunk(**values)


@pytest.mark.parametrize("path", ["../outside", "/outside", "nested/../../outside", "x\\outside", "./x", "x//y"])
def test_traversal_rejected_before_file_read(tmp_path, path):
    proxy, scope, _, _ = registered(tmp_path)
    with pytest.raises(JournalError, match="ARTIFACT_PATH_INVALID"):
        proxy.register(**{**scope, "artifact_id": "art_" + "e" * 32}, relative_path=path)


def test_changed_bytes_and_corrupted_chunk_are_quarantined(tmp_path):
    proxy, scope, manifest, path = registered(tmp_path)
    receipt = proxy.chunk(**scope, expected_sha256=manifest["sha256"], offset=0, length=4)
    receipt["data_base64"] = base64.b64encode(b"FAIL").decode()
    with pytest.raises(JournalError, match="ARTIFACT_CHUNK_INVALID"):
        validate_chunk(receipt, manifest=manifest, offset=0, length=4)
    with pytest.raises(JournalError, match="ARTIFACT_QUARANTINED"):
        validate_complete(b"1234567X", manifest)
    path.write_bytes(b"1234567X")
    with pytest.raises(JournalError, match="ARTIFACT_QUARANTINED"):
        proxy.chunk(**scope, expected_sha256=manifest["sha256"], offset=0, length=4)
