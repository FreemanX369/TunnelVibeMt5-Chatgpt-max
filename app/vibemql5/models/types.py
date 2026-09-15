from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class TerminalInfo:
    alias: str
    terminal_path: str
    metaeditor_path: str
    data_hash: str
    data_root: str
    build: int
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TerminalInfo":
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class Diagnostic:
    file: str | None
    line: int | None
    column: int | None
    severity: str
    message: str
    code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

TERMINAL_STATES = {
    "PASSED", "ANOMALY", "FAILED", "TIMEOUT", "CANCELLED",
    "INTERRUPTED", "RESOURCE_LIMIT"
}
