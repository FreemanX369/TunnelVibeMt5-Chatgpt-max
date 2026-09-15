import hashlib

import pytest

from app.vibemql5.backend_admin.core import BackendAdmin, BackendAdminError


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_backend_restore_requires_complete_cas_and_preflights_all_targets(tmp_path):
    root = tmp_path / "root"
    source_dir = root / "app" / "vibemql5"
    source_dir.mkdir(parents=True)
    first = source_dir / "first.py"
    second = source_dir / "second.py"
    original_first = b"value = 'original-first'\n"
    original_second = b"value = 'original-second'\n"
    first.write_bytes(original_first)
    second.write_bytes(original_second)

    admin = BackendAdmin(root)
    checkpoint = admin.create_checkpoint(
        ["app/vibemql5/first.py", "app/vibemql5/second.py"],
        label="restore-cas-regression",
    )
    checkpoint_id = checkpoint["payload"]["checkpoint_id"]

    candidate_first = b"value = 'candidate-first'\n"
    candidate_second = b"value = 'candidate-second'\n"
    first.write_bytes(candidate_first)
    second.write_bytes(candidate_second)

    with pytest.raises(BackendAdminError, match="RESTORE_EXPECTED_HASHES_REQUIRED"):
        admin.restore_checkpoint(checkpoint_id)

    with pytest.raises(BackendAdminError, match="RESTORE_EXPECTED_HASH_TARGET_MISMATCH"):
        admin.restore_checkpoint(
            checkpoint_id,
            expected_current_sha256_by_path={
                "app/vibemql5/first.py": _sha(candidate_first),
            },
        )

    before_first = first.read_bytes()
    before_second = second.read_bytes()
    with pytest.raises(BackendAdminError, match="CAS_MISMATCH"):
        admin.restore_checkpoint(
            checkpoint_id,
            expected_current_sha256_by_path={
                "app/vibemql5/first.py": _sha(candidate_first),
                "app/vibemql5/second.py": "0" * 64,
            },
        )
    assert first.read_bytes() == before_first
    assert second.read_bytes() == before_second

    restored = admin.restore_checkpoint(
        checkpoint_id,
        expected_current_sha256_by_path={
            "app/vibemql5/first.py": _sha(candidate_first),
            "app/vibemql5/second.py": _sha(candidate_second),
        },
    )
    assert restored["status"] == "PASS"
    assert len(restored["payload"]["restored"]) == 2
    assert first.read_bytes() == original_first
    assert second.read_bytes() == original_second
