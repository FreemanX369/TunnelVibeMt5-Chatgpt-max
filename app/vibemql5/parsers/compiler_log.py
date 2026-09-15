from __future__ import annotations
import re
from pathlib import Path
from ..models.types import Diagnostic

_PATTERNS = [
    re.compile(r"^(?P<file>.+?)\((?P<line>\d+),(?P<col>\d+)\)\s*:\s*(?P<severity>error|warning)(?:\s+(?P<code>\d+))?\s*:\s*(?P<msg>.+)$", re.I),
    re.compile(r"^(?P<file>.+?)\s*:\s*(?P<severity>error|warning)(?:\s+(?P<code>\d+))?\s*:\s*(?P<msg>.+)$", re.I),
]
_SUMMARY = re.compile(r"(?P<errors>\d+)\s+errors?,\s*(?P<warnings>\d+)\s+warnings?", re.I)

def _read_auto(path: Path) -> str:
    if not path.exists(): return ""
    data = path.read_bytes()
    if data.startswith(b"\xff\xfe"): return data.decode("utf-16-le", errors="replace")
    if data.startswith(b"\xfe\xff"): return data.decode("utf-16-be", errors="replace")
    if b"\x00" in data[:200]:
        try: return data.decode("utf-16-le", errors="replace")
        except Exception: pass
    return data.decode("utf-8-sig", errors="replace")

def parse_compiler_text(text: str) -> dict:
    diagnostics = []
    for raw in text.splitlines():
        line = raw.strip()
        for pat in _PATTERNS:
            m = pat.match(line)
            if m:
                g = m.groupdict()
                diagnostics.append(Diagnostic(
                    file=g.get("file"), line=int(g["line"]) if g.get("line") else None,
                    column=int(g["col"]) if g.get("col") else None,
                    severity=g["severity"].lower(), message=g["msg"].strip(), code=g.get("code")
                ).to_dict())
                break
    errors = sum(1 for x in diagnostics if x["severity"] == "error")
    warnings = sum(1 for x in diagnostics if x["severity"] == "warning")
    summaries = list(_SUMMARY.finditer(text))
    if summaries:
        m = summaries[-1]
        errors = max(errors, int(m.group("errors")))
        warnings = max(warnings, int(m.group("warnings")))
    return {"status": "FAILED" if errors else ("PASS_WITH_WARNINGS" if warnings else "PASSED"), "errors": errors, "warnings": warnings, "diagnostics": diagnostics}

def parse_compiler_log(path: Path) -> dict:
    result = parse_compiler_text(_read_auto(path))
    result["log_path"] = str(path)
    return result
