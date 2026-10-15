import copy

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from vibemql5.fleet.native_authorization import GatewayNativeSigner, NativeAuthorizationVerifier, NativeAuthorization
from vibemql5.fleet.job_journal import JournalError


def grant():
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    signer = GatewayNativeSigner(key, "https://fixture.example", max_authorization_ms=1000)
    binding = {"audience": signer.audience, "request_sha256": "a" * 64,
        "target": {"schema": "fleet.target/1", "device_id": "dev_" + "b" * 32,
            "terminal_id": "term_" + "c" * 32, "route_generation": 1, "terminal_generation": 1},
        "phase": "start", "node_operation_id": "node-op", "global_job_id": "fjob_" + "d" * 32,
        "local_job_id": "BT-20261003-010000-ABC123", "session_id": "node-session", "sequence": 2, "challenge": "e" * 32}
    signed = signer.issue(issued_ms=1000, expires_ms=2000, authorization_id="auth-one", **binding)
    return signed, binding, public


@pytest.mark.parametrize("field", ["audience", "request_sha256", "target", "phase", "node_operation_id", "global_job_id",
    "local_job_id", "session_id", "sequence", "challenge", "event", "issued_ms", "expires_ms", "authorization_id"])
def test_every_signature_field_tamper_denied(field):
    signed, binding, public = grant()
    corrupted = copy.deepcopy(signed)
    value = corrupted["body"][field]
    corrupted["body"][field] = {**value, "route_generation": 2} if isinstance(value, dict) else value + 1 if type(value) is int else value + "X"
    with pytest.raises(JournalError):
        NativeAuthorizationVerifier(public, binding["audience"], clock_ms=lambda: 1001).verify(corrupted, **binding)


def test_sealed_verified_proof_rechecks_exact_binding_and_expiry_at_each_effect():
    signed, binding, public = grant(); clock = [1001]
    proof = NativeAuthorizationVerifier(public, binding["audience"], clock_ms=lambda: clock[0]).verify(signed, **binding)
    assert proof.signer_public_key == public and proof.require(**binding)["phase"] == "start"
    with pytest.raises(JournalError): proof.require(**{**binding, "phase": "deploy"})
    clock[0] = 2000
    with pytest.raises(JournalError, match="NATIVE_AUTHORIZATION_EXPIRED"): proof.require(**binding)
    with pytest.raises(JournalError, match="NATIVE_AUTHORIZATION_UNVERIFIED"):
        NativeAuthorization(signed["body"], lambda: 1001, True, public)


def test_nullable_process_scope_is_signed_and_cancel_requires_exact_digest():
    signed, binding, public = grant()
    corrupted = copy.deepcopy(signed); corrupted["body"]["process_sha256"] = "a" * 64
    with pytest.raises(JournalError):
        NativeAuthorizationVerifier(public, binding["audience"], clock_ms=lambda: 1001).verify(corrupted, **binding)
    key = Ed25519PrivateKey.generate(); signer = GatewayNativeSigner(key, binding["audience"], max_authorization_ms=1000)
    with pytest.raises(JournalError, match="NATIVE_AUTHORIZATION_INVALID"):
        signer.issue(issued_ms=1000, expires_ms=2000, authorization_id="cancel", **{**binding, "phase": "cancel"})
    cancel = {**binding, "phase": "cancel", "event": "owned_terminate:0001", "process_sha256": "a" * 64}
    proof = signer.issue(issued_ms=1000, expires_ms=2000, authorization_id="cancel", **cancel)
    verifier = NativeAuthorizationVerifier(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex(),
        binding["audience"], clock_ms=lambda: 1001)
    assert verifier.verify(proof, **cancel).require(**cancel)["process_sha256"] == "a" * 64
    with pytest.raises(JournalError): verifier.verify(proof, **{**cancel, "process_sha256": "b" * 64})
