"""Crypto/schema fixture claims are synthetic; no installed profile/MT5 PASS."""
import copy
import hashlib
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from test_tip056_scoped import profile
from vibemql5.fleet.scoped_resources import capacity_source_manifest, verify_capacity_roster, DOMAIN
from vibemql5.fleet.job_journal import canonical, digest, JournalError, GatewayJobJournal


def signed_fixture(root):
    body = profile(root)
    body["source_manifest"] = capacity_source_manifest()
    body["candidate_sha256"] = digest(body["source_manifest"])
    facts = {"qualification": "PHYSICAL_WINDOWS", "candidate_sha256": body["candidate_sha256"],
        "runtime_sha256": body["runtime_sha256"], "device_id": body["device_id"], "install_epoch": body["install_epoch"],
        "capacity": 2, "terminal_roster_sha256": digest(body["terminals"]),
        "fixture_label": "SYNTHETIC_SIGNED_PROTOCOL_CLAIMS_ONLY"}
    load = canonical({**facts, "schema": "fleet.capacity-load/1", "duration_ms": 10000, "completed_jobs": 2,
        "measured": {"memory_bytes": 1000, "cpu_basis_points": 100, "p95_phase_ms": 10},
        "limits": {"memory_bytes": 2000, "cpu_basis_points": 1000, "p95_phase_ms": 100}})
    closure = canonical({**facts, "schema": "fleet.capacity-closure/1", "descendant_boundary": "EXACT_DESCENDANTS_EXITED"})
    body["load_receipt"] = {"path": "state/fleet/load.json", "sha256": hashlib.sha256(load).hexdigest()}
    body["closure_receipt"] = {"path": "state/fleet/closure.json", "sha256": hashlib.sha256(closure).hexdigest()}
    key = Ed25519PrivateKey.generate()
    signed = {"body": body, "signature": key.sign(DOMAIN + canonical(body)).hex()}
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return signed, public, load, closure


def test_exact_signed_roster_protocol_validation_without_installation(tmp_path):
    signed, public, load, closure = signed_fixture(tmp_path)
    roster = verify_capacity_roster(signed, device_id=signed["body"]["device_id"], route_generation=3,
        trusted_owner_public_key=public, load_receipt=load, closure_receipt=closure)
    assert roster.route_generation == 3 and roster.profile["capacity"] == 2
    assert not (tmp_path / "state" / "fleet" / "scoped-install.json").exists()
    changed = roster.profile; changed["capacity"] = 100
    assert roster.profile["capacity"] == 2


@pytest.mark.parametrize("change", ["signature", "capacity", "load", "closure", "device", "owner"])
def test_changed_signature_scope_or_receipt_never_grants_capacity(tmp_path, change):
    signed, public, load, closure = signed_fixture(tmp_path)
    device = signed["body"]["device_id"]
    if change == "signature": signed["signature"] = "0" * 128
    if change == "capacity": signed["body"]["capacity"] = 3
    if change == "load": load = load + b"X"
    if change == "closure": closure = closure + b"X"
    if change == "device": device = "dev_" + "f" * 32
    if change == "owner": public = "e" * 64
    with pytest.raises(JournalError):
        verify_capacity_roster(signed, device_id=device, route_generation=3,
            trusted_owner_public_key=public, load_receipt=load, closure_receipt=closure)


@pytest.mark.parametrize("change", ["missing", "extra", "two_files", "duplicate_alias", "changed_product_hash"])
def test_signed_self_consistent_incomplete_or_extra_source_bundle_is_denied(tmp_path, change):
    signed, _public, load, closure = signed_fixture(tmp_path); body = signed["body"]
    manifest = body["source_manifest"]; first = next(iter(manifest))
    if change == "missing": manifest.pop(first)
    elif change == "extra": manifest[str(tmp_path / "invented.py")] = "a" * 64
    elif change == "two_files":
        body["source_manifest"] = {k: v for k, v in manifest.items() if k.endswith(("pyproject.toml", "requirements-bootstrap.lock"))}
    elif change == "duplicate_alias":
        manifest["C:/alternate/vibemql5/" + first.split("/vibemql5/", 1)[1]] = manifest[first]
    else: manifest[first] = "a" * 64
    body["candidate_sha256"] = digest(body["source_manifest"])
    blobs = []
    for name, raw in (("load_receipt", load), ("closure_receipt", closure)):
        facts = json.loads(raw); facts["candidate_sha256"] = body["candidate_sha256"]
        raw = canonical(facts); body[name]["sha256"] = hashlib.sha256(raw).hexdigest(); blobs.append(raw)
    key = Ed25519PrivateKey.generate()
    signed = {"body": body, "signature": key.sign(DOMAIN + canonical(body)).hex()}
    with pytest.raises(JournalError):
        verify_capacity_roster(signed, device_id=body["device_id"], route_generation=3,
            trusted_owner_public_key=key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex(),
            load_receipt=blobs[0], closure_receipt=blobs[1])


def test_persisted_roster_reopen_requires_current_owner_and_original_signed_proof(tmp_path):
    signed, public, load, closure = signed_fixture(tmp_path)
    roster = verify_capacity_roster(signed, device_id=signed["body"]["device_id"], route_generation=3,
        trusted_owner_public_key=public, load_receipt=load, closure_receipt=closure)
    policy = dict(max_records=20, max_payload_bytes=262144, wait_ms=100)
    path = tmp_path / "gateway.sqlite"
    with GatewayJobJournal(path, initialize=True, capacity_owner_public_key=public, **policy) as journal:
        journal.install_capacity_roster(roster)
        assert journal.capacity_for_node(signed["body"]["device_id"], 3) == 2
    for owner in (None, "e" * 64):
        with pytest.raises(JournalError): GatewayJobJournal(path, capacity_owner_public_key=owner, **policy)
    with GatewayJobJournal(path, capacity_owner_public_key=public, **policy) as reopened:
        assert reopened.capacity_for_node(signed["body"]["device_id"], 3) == 2
        changed = reopened._meta("capacity_rosters")
        changed[signed["body"]["device_id"]]["proof"]["signed_profile"]["signature"] = "0" * 128
        reopened._meta("capacity_rosters", changed)
        with pytest.raises(JournalError): reopened.capacity_for_node(signed["body"]["device_id"], 3)
    with pytest.raises(JournalError): GatewayJobJournal(path, capacity_owner_public_key=public, **policy)


def test_unconfigured_journal_cannot_install_verified_higher_roster(tmp_path):
    signed, public, load, closure = signed_fixture(tmp_path)
    roster = verify_capacity_roster(signed, device_id=signed["body"]["device_id"], route_generation=3,
        trusted_owner_public_key=public, load_receipt=load, closure_receipt=closure)
    with GatewayJobJournal(tmp_path / "gateway.sqlite", initialize=True,
            max_records=20, max_payload_bytes=262144, wait_ms=100) as journal:
        assert journal.capacity_for_node(signed["body"]["device_id"], 3) == 1
        with pytest.raises(JournalError, match="NATIVE_CAPACITY_TRUST_UNAVAILABLE"):
            journal.install_capacity_roster(roster)
        journal.bind_capacity_owner(public)
        journal.install_capacity_roster(roster)
        with pytest.raises(JournalError): journal.bind_capacity_owner("e" * 64)
        assert journal.capacity_for_node(signed["body"]["device_id"], 3) == 2
