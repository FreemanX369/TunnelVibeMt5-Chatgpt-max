from __future__ import annotations
import json, os
from pathlib import Path
from typing import Any
from .errors import ConfigError

DEFAULT_WINDOWS_ROOT = Path(r"C:\VibeMQL5")

def default_root() -> Path:
    raw = os.environ.get("VIBEMQL5_ROOT")
    if raw:
        return Path(raw)
    if os.name == "nt":
        return DEFAULT_WINDOWS_ROOT
    # Dev/test: repo root from app/vibemql5/config.py
    return Path(__file__).resolve().parents[2]

def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise ConfigError(f"Missing configuration: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc

def load_settings(root: Path | None = None) -> dict[str, Any]:
    root = Path(root or default_root())
    data = load_json(root / "config" / "settings.json")
    required = ["resource_guard", "retention", "jobs"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ConfigError(f"settings.json missing keys: {missing}")
    return data

def load_preset(name: str, root: Path | None = None) -> dict[str, Any]:
    root = Path(root or default_root())
    if not name.replace("-", "").replace("_", "").isalnum():
        raise ConfigError("Invalid preset name")
    return load_json(root / "config" / "presets" / f"{name}.json")
