"""Explicit quiet migration of a disposable test root. Never imported by runtime."""
from pathlib import Path
import uuid

from vibemql5.core.jobs import _atomic_write_json
from vibemql5.core.native_ownership import INSTALL_SCHEMA, SCHEMA, OwnershipAuthority


def install_closed(root: Path, *, epoch: str | None = None, stop_after: int = 3):
    authority = OwnershipAuthority(root)
    epoch = epoch or uuid.uuid4().hex
    with authority.transaction():
        if authority.path.exists() or authority.marker_path.exists():
            raise AssertionError("Fixture installation must be explicit and fresh")
        marker = {"schema": INSTALL_SCHEMA, "epoch": epoch, "disposition": "MIGRATING"}
        _atomic_write_json(authority.marker_path, marker)
        if stop_after == 1:
            return authority
        _atomic_write_json(authority.path, {"schema": SCHEMA, "epoch": epoch,
            "generation": 1, "disposition": "CLOSED", "phase": "CLOSED", "token": "",
            "operation_id": "", "kind": "", "parent": None, "worker": None, "descendants": "NONE"})
        if stop_after == 2:
            return authority
        _atomic_write_json(authority.marker_path, {**marker, "disposition": "READY"})
        authority.require_closed()
    return authority
