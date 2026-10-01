from __future__ import annotations

from .identity import IdentityError, IdentityRegistry, _positive


def validate_local_target(root, terminals, target: dict, *, capability: str = "inventory") -> dict:
    """Resolve exactly one current local binding. This API never dispatches work."""
    if not isinstance(target, dict) or target.get("schema") != "fleet.target/1":
        raise IdentityError("TARGET_MISMATCH", "Expected fleet.target/1 reference")
    if set(target) - {"schema", "device_id", "terminal_id", "terminal_generation", "route_generation"}:
        raise IdentityError("TARGET_MISMATCH", "Unsupported target fields")
    registry = IdentityRegistry(root)
    record = registry.load()
    if record is None:
        raise IdentityError("IDENTITY_UNENROLLED", "Local registry is absent")
    if target.get("device_id") != record["device_id"]:
        raise IdentityError("TARGET_UNKNOWN", "Unknown local device")
    row = next((row for row in record["terminals"] if row["terminal_id"] == target.get("terminal_id")), None)
    if row is None:
        raise IdentityError("TARGET_UNKNOWN", "Unknown local terminal")
    if not _positive(target.get("terminal_generation")) or target["terminal_generation"] != row["terminal_generation"]:
        raise IdentityError("TARGET_MISMATCH", "Terminal generation mismatch")
    overlay = registry.overlay(terminals).get(row["alias"].upper())
    if not overlay:
        raise IdentityError("TARGET_MISMATCH", "Enrolled alias is not in current configuration")
    if overlay["identity_revision"] != record["identity_revision"] or any(
            overlay[field] != target.get(field) for field in ("device_id", "terminal_id", "terminal_generation")):
        raise IdentityError("TARGET_MISMATCH", "Identity changed during local validation")
    status = overlay["identity_status"]
    if status != "ENROLLED":
        code = status if status in {"RESOURCE_CONFLICT", "IDENTITY_INVALID"} else "TARGET_MISMATCH"
        raise IdentityError(code, f"Local identity status is {status}")
    if overlay["resource_qualification"] != "QUALIFIED":
        raise IdentityError("TARGET_MISMATCH", "Physical binding is UNQUALIFIED")
    if target.get("route_generation") is not None or capability != "inventory":
        raise IdentityError("ROUTED_NATIVE_NOT_ENABLED", "M0 authorizes local inventory validation only")
    return {**overlay, "alias": row["alias"], "binding": dict(row["binding"])}
