"""Explicit provision-only operator step; never starts a gateway, node or SDK."""
import hashlib
import ipaddress
import json
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(r"C:\VibeMQL5")
ROOT = BASE / "ops/windows/fleet-pilot-745147f-20261016-a"
HEAD = "745147f525caefbec66505e5cdb6a4fb7013c2d7"
MANIFEST_SHA = "5ae7d19d5a7019936c0b21611a8c0825374dc96527d69b6cb37eac69a2e7758a"
ORIGIN = "https://localhost:8443"


def configurations(root, source, gateway_public_key):
    def template(name):
        return json.loads((source / "docs/fleet-v1/config" / (name + ".example.json")).read_bytes())
    runtime = root / "runtime"
    secret = runtime / "secrets"
    gateway, node, client = (template(name) for name in ("gateway", "node-readonly", "client"))
    for config in (gateway, node, client):
        config["origin"] = ORIGIN
        config["fleet_policy"]["max_targets"] = 5
    gateway.update(listen_host="127.0.0.1", listen_port=8443,
                   certificate_file=str(secret / "gateway-chain.pem"),
                   tls_key_file=str(secret / "gateway-tls-key.pem"),
                   owner_token_file=str(secret / "owner-token.txt"),
                   authority_key_file=str(secret / "gateway-authority.pem"))
    gateway["control_policy"]["max_devices"] = 1
    for config in (gateway, node):
        config["journal_policy"]["max_payload_bytes"] = 262144
    for field, name in (("control_path", "control.sqlite"), ("domain_path", "domain.sqlite"),
                        ("jobs_path", "jobs.sqlite"), ("principal_path", "principals.json")):
        gateway[field] = str(runtime / "gateway" / name)
    node.update(root=str(BASE), ca_file=str(secret / "operator-ca.pem"),
                node_key_file=str(secret / "node-ed25519.pem"),
                gateway_public_key=gateway_public_key,
                session_id="pilot-745147f-20261016-a", max_inventory_rows=5)
    for field, name in (("jobs_path", "jobs.sqlite"), ("domain_path", "domain.sqlite"),
                        ("transport_path", "transport.sqlite")):
        node[field] = str(runtime / "node" / name)
    node["artifact_policy"]["installation_id"] = "pilot-745147f-20261016-a"
    client.update(ca_file=str(secret / "operator-ca.pem"),
                  owner_token_file=str(secret / "owner-token.txt"))
    return {"gateway.json": gateway, "node.json": node, "owner-client.json": client}


def tls_material():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    now = datetime.now(timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    server_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TunnelVibe single-VPS pilot CA")])
    server_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=7))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .sign(ca_key, hashes.SHA256()))
    certificate = (x509.CertificateBuilder().subject_name(server_name).issuer_name(ca_name)
                   .public_key(server_key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=7))
                   .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                   .add_extension(x509.SubjectAlternativeName([
                       x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
                   .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                   .sign(ca_key, hashes.SHA256()))
    return {"operator-ca.pem": ca.public_bytes(serialization.Encoding.PEM),
            "gateway-chain.pem": certificate.public_bytes(serialization.Encoding.PEM),
            "gateway-tls-key.pem": server_key.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8, serialization.NoEncryption())}


def main():
    if sys.argv[1:] != ["--provision"]:
        print(json.dumps({"mode": "PLAN_ONLY", "root": str(ROOT), "origin": ORIGIN,
                          "protected_files": 9, "starts_services": False, "imports_sdk": False}))
        return 0
    if os.name != "nt":
        raise RuntimeError("WINDOWS_REQUIRED")
    raw = (ROOT / "STAGING-MANIFEST.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA:
        raise RuntimeError("STAGING_MANIFEST_MISMATCH")
    manifest = json.loads(raw)
    if manifest["source_head"] != HEAD or len(manifest["files"]) != 93:
        raise RuntimeError("STAGING_SCOPE_MISMATCH")
    for entry in manifest["files"]:
        path = BASE / entry["target_path"]
        if not path.resolve().is_relative_to((ROOT / "source").resolve()):
            raise RuntimeError("STAGING_PATH_INVALID")
        content = path.read_bytes()
        if len(content) != entry["bytes"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise RuntimeError("STAGING_PAYLOAD_MISMATCH")
    sys.path.insert(0, str(ROOT / "source/app"))
    from vibemql5.fleet import node_keys as keys
    from vibemql5.adapters.fleet_cli import gateway_factory, operator_server_context
    from vibemql5.adapters.fleet_client_tools import FleetClientFacade, operator_configuration, operator_ssl_context
    runtime = ROOT / "runtime"
    runtime.mkdir(exist_ok=False)
    held = []
    try:
        held.append(keys._windows_hold_private_directory(runtime))
        for name in ("secrets", "gateway", "node"):
            directory = runtime / name
            directory.mkdir(exist_ok=False)
            held.append(keys._windows_hold_private_directory(directory))
        secret = runtime / "secrets"
        def protected_write(name, content):
            descriptor = keys._windows_create(keys._path(secret / name))
            try:
                keys._windows_acl(descriptor, set_restrictive=True)
                keys._check(descriptor)
                remaining = memoryview(content)
                while remaining:
                    count = os.write(descriptor, remaining)
                    if count <= 0:
                        raise RuntimeError("PROTECTED_WRITE_FAILED")
                    remaining = remaining[count:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        gateway_key = keys.create_node_key(secret / "gateway-authority.pem")
        node_key = keys.create_node_key(secret / "node-ed25519.pem")
        for name, content in tls_material().items():
            protected_write(name, content)
        protected_write("owner-token.txt", secrets.token_urlsafe(32).encode("ascii"))
        configs = configurations(ROOT, ROOT / "source", gateway_key["public_key"])
        for name, config in configs.items():
            protected_write(name, json.dumps(config, indent=2).encode("utf-8"))
        for name in configs:
            operator_configuration(secret / name)
        gateway_factory(configs["gateway.json"], initialize=False)  # Validate; do not invoke returned factory.
        operator_server_context(configs["gateway.json"]["certificate_file"], configs["gateway.json"]["tls_key_file"])
        context = operator_ssl_context(secret / "operator-ca.pem")
        if not context.check_hostname:
            raise RuntimeError("TLS_HOSTNAME_CHECK_REQUIRED")
        info = FleetClientFacade.from_config(secret / "owner-client.json").server_info()
        if info["tool_count"] != 31:
            raise RuntimeError("FLEET_CATALOG_MISMATCH")
        receipt = {"status": "PROVISIONED_NOT_ACTIVATED", "source_head": HEAD, "origin": ORIGIN,
                   "protected_files": 9, "gateway_public_key": gateway_key["public_key"],
                   "node_public_key": node_key["public_key"], "optional_tool_count": 31,
                   "sdk_qualifications": [], "native_capacity": "NOT_QUALIFIED", "services_started": False}
        with (runtime / "PROVISION-RECEIPT.json").open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps(receipt))
        return 0
    finally:
        for descriptor in reversed(held):
            os.close(descriptor)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"status": "FAILED_PRESERVE_PARTIAL", "error_type": type(error).__name__}))
        raise SystemExit(1)
