from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
import hashlib, json, os, time, uuid

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def utcish_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")

def new_id(prefix: str) -> str:
    return f"{prefix}-{utcish_stamp()}-{uuid.uuid4().hex[:8].upper()}"

@dataclass(frozen=True)
class FileMeta:
    path: str
    sha256: str
    bytes: int

    @classmethod
    def from_path(cls, path: Path) -> "FileMeta":
        st = path.stat()
        return cls(str(path), sha256_file(path), st.st_size)

@dataclass
class Receipt:
    operation_id: str
    operation: str
    status: str
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

def write_json_atomic(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}-{uuid.uuid4().hex}")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)
