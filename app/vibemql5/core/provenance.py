from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..config import default_root
from ..contracts import MCP_TOOL_CATALOG_SHA256, MCP_TOOL_COUNT


def _mcp_catalog_authority() -> dict[str, Any]:
    return {
        "mcp_tool_count": MCP_TOOL_COUNT,
        "mcp_tool_catalog_sha256": MCP_TOOL_CATALOG_SHA256,
        "mcp_tool_catalog_source": "contracts.py",
    }


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_bridge_provenance(root: Path | None = None) -> dict[str, Any]:
    base = Path(root or default_root())
    p = base / "config" / "build-provenance.json"
    if not p.is_file():
        packaged_root = Path(__file__).resolve().parents[3]
        packaged = packaged_root / "config" / "build-provenance.json"
        if packaged.is_file() and packaged.resolve() != p.resolve():
            p = packaged
        else:
            raise FileNotFoundError(f"BRIDGE_PROVENANCE_MISSING: {p}")
    data = json.loads(p.read_text(encoding="utf-8-sig"))
    required = ("schema_version", "bridge_version", "bridge_build")
    if not isinstance(data, dict) or any(not data.get(k) for k in required):
        raise ValueError("BRIDGE_PROVENANCE_INVALID")
    # TIP-031: the MCP catalog is generated from contracts.py. The packaged
    # build-provenance file identifies the bridge build, but catalog count/hash
    # must follow the runtime contract so supervisor/watchdog state cannot keep
    # advertising a stale pre-TIP-027 tool count.
    return {**data, **_mcp_catalog_authority()}


def producer_identity(path: Path, component: str, schema: str = "1.0") -> dict[str, Any]:
    p = Path(path).resolve()
    digest = sha256_file(p)
    return {
        "producer_component": str(component),
        "producer_schema": str(schema),
        "producer_build": f"sha256:{digest[:12]}",
        "producer_sha256": digest,
    }


def validate_state_provenance(
    root: Path,
    state: dict[str, Any],
    producer_path: Path,
    component: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    try:
        canonical = load_bridge_provenance(root)
    except Exception as exc:
        return {"fresh": False, "reasons": ["CANONICAL_PROVENANCE_UNAVAILABLE"], "error": str(exc)}
    try:
        producer = producer_identity(producer_path, component, str(state.get("producer_schema") or "1.0"))
    except Exception as exc:
        return {"fresh": False, "reasons": ["PRODUCER_ARTIFACT_UNAVAILABLE"], "error": str(exc)}

    if str(state.get("bridge_build") or "") != str(canonical["bridge_build"]):
        reasons.append("BRIDGE_BUILD_STALE")
    if str(state.get("bridge_version") or "") != str(canonical["bridge_version"]):
        reasons.append("BRIDGE_VERSION_STALE")
    expected_catalog = _mcp_catalog_authority()
    try:
        state_tool_count = int(state.get("mcp_tool_count"))
    except (TypeError, ValueError):
        state_tool_count = -1
    if state_tool_count != int(expected_catalog["mcp_tool_count"]):
        reasons.append("MCP_TOOL_COUNT_STALE")
    if (
        str(state.get("mcp_tool_catalog_sha256") or "").lower()
        != str(expected_catalog["mcp_tool_catalog_sha256"])
    ):
        reasons.append("MCP_TOOL_CATALOG_SHA_STALE")
    if str(state.get("producer_component") or "") != component:
        reasons.append("PRODUCER_COMPONENT_MISMATCH")
    if str(state.get("producer_sha256") or "").lower() != producer["producer_sha256"]:
        reasons.append("PRODUCER_SHA_STALE")
    if str(state.get("producer_build") or "") != producer["producer_build"]:
        reasons.append("PRODUCER_BUILD_STALE")
    return {
        "fresh": not reasons,
        "reasons": reasons,
        "canonical": canonical,
        "expected_catalog": _mcp_catalog_authority(),
        "expected_producer": producer,
    }
