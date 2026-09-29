from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .core import BackendAdmin
from ..core.jobs import _exclusive_file_lock


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    root = Path(sys.argv[1]).resolve()
    run_id = str(sys.argv[2])
    admin = BackendAdmin(root)
    path = admin._test_run_path(run_id)
    lock = admin.test_run_root / f"{run_id}.lock"
    if not path.is_file():
        return 3

    with _exclusive_file_lock(lock, timeout_seconds=10.0):
        record = json.loads(path.read_text(encoding="utf-8"))
        suite = str(record.get("suite") or "")
        if record.get("state") not in {"STARTING", "RUNNING"}:
            return 0

    try:
        result = admin.run_tests(suite)
        final_state = "PASSED" if result.get("status") == "PASS" else "FAILED"
        reason_code = None
    except Exception as exc:
        result = {
            "status": "FAIL",
            "suite": suite,
            "exception_type": type(exc).__name__,
            "error": str(exc),
        }
        final_state = "FAILED"
        reason_code = "TEST_RUN_EXCEPTION"

    with _exclusive_file_lock(lock, timeout_seconds=10.0):
        current = json.loads(path.read_text(encoding="utf-8"))
        current["state"] = final_state
        current["result"] = result
        current["reason_code"] = reason_code
        current["finished_at_utc"] = _now()
        admin._write_test_run(path, current)
    return 0 if final_state == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
