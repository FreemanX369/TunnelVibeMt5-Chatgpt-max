"""Bounded, byte-exact PNG archive for one-call live chart exports."""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

MAX_CHART_FILES = 64
MAX_CHART_ARCHIVE_BYTES = 64_000_000


def archive_chart_png(root: Path, meta: dict, png: bytes) -> str:
    """Return a relative exports path; caller holds the shared mutation lease."""
    if not png.startswith(b"\x89PNG\r\n\x1a\n") or not 24 <= len(png) <= 8_000_000:
        raise ValueError("LIVE_CHART_EXPORT_INVALID_PNG")
    chart = meta.get("chart") or {}
    chart_id = chart.get("chart_id")
    if isinstance(chart_id, bool) or not isinstance(chart_id, int) or chart_id <= 0:
        raise ValueError("LIVE_CHART_EXPORT_INVALID_CHART_ID")
    safe = lambda value: re.sub(r"[^A-Za-z0-9_-]", "_", str(value or ""))[:32] or "chart"
    root = Path(root).resolve()
    exports = root / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    if exports.is_symlink() or not exports.resolve().is_relative_to(root):
        raise ValueError("LIVE_CHART_EXPORT_ROOT_UNSAFE")
    folder = exports / "live-charts"
    folder.mkdir(exist_ok=True)
    if folder.is_symlink() or not folder.resolve().is_relative_to(exports.resolve()):
        raise ValueError("LIVE_CHART_EXPORT_FOLDER_UNSAFE")
    name = f"MT5-2_{safe(chart.get('symbol'))}_{safe(chart.get('timeframe'))}_{chart_id}_{uuid.uuid4().hex[:16]}.png"
    target = folder / name
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(png)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise

    # Downloads are short-lived; bound disk use without touching files outside this archive.
    files = sorted((p for p in folder.glob("MT5-2_*.png") if p.is_file() and not p.is_symlink()),
                   key=lambda p: (p.stat().st_mtime_ns, p.name))
    total = sum(p.stat().st_size for p in files)
    while len(files) > MAX_CHART_FILES or total > MAX_CHART_ARCHIVE_BYTES:
        old = files.pop(0)
        total -= old.stat().st_size
        old.unlink()
    return f"live-charts/{name}"
